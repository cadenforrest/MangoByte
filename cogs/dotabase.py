import json
import random
import re
from textwrap import indent

import disnake
import feedparser
import utils.drawing.dota as drawdota
import utils.drawing.imagetools as imagetools
import utils.other.rsstools as rsstools
from disnake.ext import commands, tasks
from sqlalchemy import and_, desc, or_
from sqlalchemy.sql.expression import func
from utils.command.clip import *
from utils.command.commandargs import *
from utils.tools.globals import httpgetter, logger, settings
from utils.tools.helpers import *

from cogs.audio import AudioPlayerNotFoundError, Audio
from dotabase import *

from cogs.mangocog import *

CRITERIA_ALIASES = read_json(settings.resource("json/criteria_aliases.json"))

session = dotabase_session()

CURRENT_DOTA_PATCH_NUMBER = session.query(Patch).order_by(desc(Patch.timestamp)).first().number

ABILITY_KEY_MAP = {
	"q": 1,
	"w": 2,
	"e": 3,
	"d": 4,
	"f": 5,
	"r": 4 # the last ability in the list, except for invoker
}
for i in range(1, 20):
	ABILITY_KEY_MAP[str(i)] = i
	
# registers the method as the custom converter for that class
def register_custom_converter(cls, method):
	commands.ParamInfo._registered_converters[cls] = method
	cls.__discord_converter__ = method

async def convert_hero(inter: disnake.CmdInter, text: str) -> Hero:
	dota_cog: Dotabase
	dota_cog = inter.bot.get_cog("Dotabase")
	hero = dota_cog.lookup_hero(text)
	if hero is None:
		raise CustomBadArgument(UserError(f"Couldn't find a hero called '{text}'"))
	return hero
register_custom_converter(Hero, convert_hero)


# A variable that can specify a filter on a query
class QueryVariable():
	def __init__(self, name, aliases, query_filter, prefix=None):
		self.name = name
		self.aliases = aliases
		self.query_filter = query_filter
		self.prefix = prefix or ";"
		self.value = None

	def __repr__(self):
		if self.value is None:
			return self.name + " not set"
		else:
			return self.name + " = " + self.value

	def apply_filter(self, query):
		return self.query_filter(query, self.value)


# Filters a query for rows containing a column that contains the value in a | separated list
def query_filter_list(query, column, value, separator="|"):
	return query.filter(or_(column.like(f"%|{value}"), column.like(f"{value}|%"), column.like(f"%|{value}|%"), column.like(value)))


class Dotabase(MangoCog):
	"""For information about the game Dota 2 [Patch **{CURRENT_DOTA_PATCH_NUMBER}**]

	Interfaces with [dotabase](http://github.com/mdiller/dotabase). Check out [dotabase.dillerm.io](http://dotabase.dillerm.io) if you want to see an old website I built that interfaces with dotabase."""
	def __init__(self, bot):
		MangoCog.__init__(self, bot)
		self.session = session
		self.hero_stat_categories = read_json(settings.resource("json/hero_stats.json"))
		self.hero_aliases = {}
		self.item_aliases = {}
		self.leveled_hero_stats = [] # by level (0 is null, and 1-30 are filled in)
		self.hero_regex = ""
		self.item_regex_1 = ""
		self.item_regex_2 = ""
		self.patches_regex = ""
		self.build_helpers()
		self.vpkurl = "http://dotabase.dillerm.io/dota-vpk"
		drawdota.init_dota_info(self.get_hero_infos(), self.get_item_infos(), self.get_ability_infos(), self.vpkurl)

	def build_helpers(self):
		def clean_input(t):
			return re.sub(r'[^a-z1-9\s]', r'', str(t).lower())
		for hero in session.query(Hero):
			aliases = hero.aliases.split("|")
			for alias in aliases:
				self.hero_aliases[alias] = hero.id
				self.hero_aliases[alias.replace(" ", "")] = hero.id

		patches_patterns = []
		for patch in session.query(Patch).filter(Patch.timestamp != None):
			patches_patterns.append(patch.number.replace(".", "\\."))
		self.patches_regex = f"(?:{'|'.join(patches_patterns)})"

		item_patterns = []
		secondary_item_patterns = []
		for item in session.query(Item).filter(~Item.localized_name.contains("Recipe")):
			aliases = item.aliases.split("|")
			aliases.append(clean_input(item.localized_name))
			for alias in aliases:
				if alias not in self.item_aliases:
					self.item_aliases[alias] = item.id
					self.item_aliases[alias.replace(" ", "")] = item.id
			pattern = re.sub(r"[^a-z' ]", "", item.localized_name.lower())
			pattern = pattern.replace("'", "'?")
			if " " in pattern:
				secondary_item_patterns.extend(pattern.split(" "))
			item_patterns.append(pattern)
		self.item_regex_1 = f"(?:{'|'.join(item_patterns)})"
		item_patterns.extend(secondary_item_patterns)
		self.item_regex_2 = f"(?:{'|'.join(item_patterns)})"

		pattern_parts = {}
		for alias in self.hero_aliases:
			parts = []
			if len(alias) > 2:
				tempstring = ""
				for i in range(2, len(alias)):
					tempstring += alias[i]
					parts.append(tempstring)
			prefix = alias[:2]
			if not prefix in pattern_parts:
				pattern_parts[prefix] = []
			pattern_parts[prefix].extend(parts)
		patterns = []
		for prefix in pattern_parts:
			parts = list(set(pattern_parts[prefix]))
			parts = sorted(parts, key=lambda p: len(p), reverse=True)
			if len(parts) > 0:
				result = f"{prefix}(?:{'|'.join(parts)})?"
				patterns.append(result)
			else:
				patterns.append(prefix)
		self.hero_regex = f"(?:{'|'.join(patterns)})"


		for category in self.hero_stat_categories:
			for stat in category["stats"]:
				if "lambda" in stat:
					stat["lambda"] = eval(stat["lambda"])
		all_heroes = session.query(Hero).all()
		self.leveled_hero_stats.append(0)
		for level in range(1, 31):
			all_hero_stats = []
			for hero in all_heroes:
				hero_stats = {} #vars(hero)
				hero_stats["id"] = hero.id
				hero_stats["level"] = level
				for category in self.hero_stat_categories:
					for stat in category["stats"]:
						if "lambda" in stat:
							value = stat["lambda"](hero, hero_stats)
							hero_stats[stat["stat"]] = value
						else:
							hero_stats[stat["stat"]] = vars(hero)[stat["stat"]]
				all_hero_stats.append(hero_stats)
			self.leveled_hero_stats.append(all_hero_stats)

	def get_wiki_url(self, obj):
		if isinstance(obj, Hero):
			wikiurl = obj.localized_name
		elif isinstance(obj, Ability):
			wikiurl = f"{obj.hero.localized_name}#{obj.localized_name}"
		elif isinstance(obj, Item):
			wikiurl = obj.localized_name

		wikiurl = wikiurl.replace(" ", "_").replace("'", "%27")
		return f"http://dota2.gamepedia.com/{wikiurl}"
	
	# gets the patch a match took place in, else None
	def get_match_patch(self, match):
		query = session.query(Patch)
		timestamp = datetime.datetime.fromtimestamp(match['start_time'], tz=datetime.timezone.utc)
		query = query.filter(Patch.timestamp <= timestamp)
		query = query.order_by(desc(Patch.timestamp))
		query = query.limit(1)
		if query.count() > 0:
			return query.first().number
		else:
			return None

	def lookup_hero(self, hero):
		if not hero:
			return None
		if isinstance(hero, str):
			hero = hero.strip()
		hero_id = self.lookup_hero_id(hero)
		if hero_id:
			return session.query(Hero).filter(Hero.id == hero_id).first()
		else:
			return None

	def lookup_hero_id(self, text):
		if isinstance(text, int) or text.isdigit():
			query = session.query(Hero).filter(Hero.id == int(text))
			return int(text) if query.count() > 0 else None
		text = re.sub(r'[^a-z^\s]', r'', text.lower())
		if text == "":
			return None
		if text in self.hero_aliases:
			return self.hero_aliases[text]
		for hero in session.query(Hero):
			if hero.localized_name.lower().startswith(text):
				return hero.id
		for hero in self.hero_aliases:
			if hero.startswith(text):
				return self.hero_aliases[hero]
		for hero in self.hero_aliases:
			if text in hero:
				return self.hero_aliases[hero]
		return None

	def lookup_ability(self, text, full_check=True):
		if isinstance(text, str):
			text = text.strip()
		ability_query = session.query(Ability).filter(Ability.hero_id != None)
		if isinstance(text, int) or text.isdigit():
			return ability_query.filter(Ability.id == int(text)).first()
		def clean_input(t):
			return re.sub(r'[^a-z1-9\s]', r'', str(t).lower())
		text = clean_input(text)
		if text == "":
			return None
		for ability in ability_query:
			if clean_input(ability.localized_name) == text:
				return ability
		if full_check:
			for ability in ability_query:
				cleaned_name = clean_input(ability.localized_name)
				if cleaned_name.startswith(text):
					return ability
				cleaned_name = cleaned_name.replace(" ", "")
				if cleaned_name == text.replace(" ", ""):
					return ability
			for ability in ability_query:
				name = clean_input(ability.localized_name)
				if " " in name:
					for part in name.split(" "):
						if part.startswith(text):
							return ability
			for key in text.split(" "):
				if key in ABILITY_KEY_MAP:
					text = re.sub(f'\\b{key}\\b', '', text)
					hero = self.lookup_hero(text)
					if hero is None:
						return None
					ability_position = ABILITY_KEY_MAP[key]
					# use this instead of directly using ability_slot because there are some filler generic_ability things
					abilities = hero.abilities
					if ability_position > len(abilities):
						raise UserError(f"{hero.localized_name} doesn't have that many abilities")
					if key == "r": # if is ultimate and not invoker, get last ability in list
						def filter_ulti(ability):
							for bad_behavior in [ "not_learnable", "hidden" ]:
								if bad_behavior in (ability.behavior or ""):
									return False
							return True
						abilities = list(filter(filter_ulti, abilities))
						ability_position = len(abilities)
					return abilities[ability_position - 1]
		return None

	def lookup_item(self, item, full_check=True):
		if not item:
			return None
		if isinstance(item, str):
			item = item.strip()
		item_id = self.lookup_item_id(item, full_check)
		if item_id:
			return session.query(Item).filter(Item.id == item_id).first()
		else:
			return None

	def lookup_item_id(self, text, full_check=True):
		item_query = session.query(Item)
		if "recipe" not in text.lower():
			item_query = item_query.filter(~Item.localized_name.contains("recipe"))
			item_query = item_query.filter(~Item.localized_name.contains("Recipe"))
		if isinstance(text, int) or text.isdigit():
			return int(text)
		def clean_input(t):
			return re.sub(r'[^a-z1-9\s]', r'', str(t).lower())
		text = clean_input(text)
		if text == "":
			return None
		for item in item_query:
			if clean_input(item.localized_name) == text:
				return item.id
		if text in self.item_aliases:
			return self.item_aliases[text]

		if full_check:
			for item in self.item_aliases:
				if item.startswith(text):
					return self.item_aliases[item]
			for item in self.item_aliases:
				if text in item:
					return self.item_aliases[item]
		return None

	def lookup_patch(self, patch_name):
		query = session.query(Patch).filter(Patch.number == patch_name)
		if query.count() > 0:
			return query.first()
		else:
			return None

	def lookup_nth_patch(self, n):
		query = session.query(Patch).order_by(desc(Patch.timestamp))
		if n == 1: 
			# assume user wants latest MAJOR patch
			for patch in query:
				if not re.search(r"[a-zA-Z]", patch.number):
					return patch
		if n > query.count() or n < 0:
			return None
		else:
			return query.all()[n - 1]

	def lookup_patch_bounds(self, patch_name):
		query = session.query(Patch).order_by(Patch.timestamp)
		start = None
		end = None

		for patch in query:
			if start is None:
				if patch.number == patch_name:
					start = patch.timestamp
			else:
				if re.sub(r"[a-z]", "", patch.number) != patch_name:
					end = patch.timestamp
					break
		if end is None:
			end = datetime.datetime.now()

		return (start, end)


	def get_hero_infos(self):
		result = {}
		for hero in session.query(Hero):
			result[hero.id] = {
				"name": hero.localized_name,
				"full_name": hero.full_name,
				"icon": self.vpkurl + hero.icon,
				"attr": hero.attr_primary,
				"portrait": self.vpkurl + hero.portrait,
				"image": self.vpkurl + hero.image,
				"emoji": str(self.get_emoji(f"dota_hero_{hero.name}")),
				"roles": dict(zip(hero.roles.split("|"), map(int, hero.role_levels.split("|"))))
			}
			# role_values = list(map(int, hero.role_levels.split("|")))
			# rv_sum = sum(role_values)
			# role_values = list(map(lambda x: x / rv_sum, role_values))
			# result[hero.id]["roles"] = dict(zip(hero.roles.split("|"), role_values))
		result[0] = {
			"name": "Unknown",
			"full_name": "unknown_hero",
			"icon": self.vpkurl + "/panorama/images/heroes/icons/npc_dota_hero_antimage_png.png",
			"attr": "strength",
			"portrait": self.vpkurl + "/panorama/images/heroes/selection/npc_dota_hero_default_png.png",
			"image": self.vpkurl + "/panorama/images/heroes/npc_dota_hero_default_png.png",
			"emoji": "unknown_hero",
			"roles": {}
		}
		return result

	def get_item_infos(self):
		result = {}
		for item in session.query(Item):
			if item.icon is None:
				continue
			result[item.id] = {
				"name": item.localized_name,
				"icon": self.vpkurl + item.icon,
			}
		return result

	def get_ability_infos(self):
		result = {}
		for ability in session.query(Ability):
			if ability.icon is None:
				continue
			result[ability.id] = {
				"name": ability.localized_name,
				"icon": self.vpkurl + ability.icon,
				"slot": ability.slot,
				"entity": ability
			}
		return result

	def get_chat_wheel_infos(self):
		result = {}
		for message in session.query(ChatWheelMessage):
			result[message.id] = {
				"name": message.name,
				"message": message.message if message.message else message.name.replace("_", " ") + " (spray)",
				"is_sound": message.sound != None,
				"sound": self.vpkurl + message.sound if message.sound else None
			}
		return result

	def get_chatwheel_sound_clip(self, text):
		message = self.get_chatwheel_sound(text)
		if message:
			return f"dotachatwheel:{message.id}"
		else:
			return None

	def get_chatwheel_sound(self, text, loose_fit=False):
		def simplify(t):
			t = re.sub(r"[?!',！？.-]", "", t.lower())
			return re.sub(r"[_，]", " ", t)
		text = simplify(text)
		if text == "":
			return None
		if text.startswith("dotachatwheel:"):
			text = text.replace("dotachatwheel:", "")
		if text.isdigit():
			query = session.query(ChatWheelMessage).filter_by(id=int(text)).filter(ChatWheelMessage.sound != None)
			if query.count() > 0:
				return query.first()

		for message in session.query(ChatWheelMessage):
			if message.sound:
				strings = list(map(simplify, [ message.name, message.message, message.label ]))
				if text in strings:
					return message
				if loose_fit:
					for string in strings:
						if text.replace(" ", "") == string.replace(" ", ""):
							return message
					for string in strings:
						if text in string:
							return message
		return None

	async def play_response(self, response, clip_ctx: ClipContext):
		return await self.play_clip(f"dota:{response.fullname}", clip_ctx)

	# used for getting the right response for dota clips
	def get_response(self, responsename):
		response = session.query(Response).filter(Response.fullname == responsename).first()
		if response:
			return response
		# to support legacy clips that used name instead of fullname
		return session.query(Response).filter(Response.name == responsename).first()

	# Plays a random response from a query
	async def play_response_query(self, query, clip_ctx: ClipContext):
		return await self.play_response(query.order_by(func.random()).first(), clip_ctx)

	@Audio.play.sub_command(name="dota")
	async def play_dota(self, inter: disnake.CmdInter, text: str = None, hero: Hero = None, criteria: commands.option_enum(CRITERIA_ALIASES) = None):
		"""Plays a dota response. Try '/clips dota' for a similar command that returns a list

		Parameters
		----------
		text: Some text contained within the response you're searching for
		hero: A dota hero that says this clip
		criteria: An action or situation that causes the hero to say this clip
		"""
		query = await self.smart_dota_query(text, hero=hero, criteria=criteria)

		if query is None:
			await inter.send("No responses found! 😱")
		else:
			clip = await self.play_response_query(query, inter)
			await self.print_clip(inter, clip)
	
	@Audio.clips.sub_command(name="dota")
	async def clips_dota(self, inter: disnake.CmdInter, text: str = None, hero: Hero = None, criteria: commands.option_enum(CRITERIA_ALIASES) = None, page: commands.Range[1, 10] = 1):
		"""Plays a dota response

		Parameters
		----------
		text: Some text contained within the response you're searching for
		hero: A dota hero that says this clip
		criteria: An action or situation that causes the hero to say this clip
		page: Which page of clips to view
		"""
		query = await self.smart_dota_query(text, hero=hero, criteria=criteria)

		clipids = []
		cliptext = []
		response_limit = 200
		if query is not None:
			query = query.limit(response_limit)
			for response in query.all():
				clipids.append(f"dota:{response.fullname}")
				text = response.text
				sizelimit = 45
				if len(text) > sizelimit:
					text = text[:sizelimit - 3] + "..."
				cliptext.append(text)
		audio_cog = self.bot.get_cog("Audio")
		await audio_cog.clips_pager(inter, "Dota Hero Responses", clipids, cliptext, page=page, more_pages=len(clipids) == response_limit)

	async def smart_dota_query(self, keyphrase, hero: Hero = None, criteria: str = None, exact = False):
		if keyphrase is None:
			keyphrase = ""
		keyphrase = keyphrase.lower()
		keyphrase = " ".join(keyphrase.split(" "))

		basequery = session.query(Response)

		if hero:
			basequery = basequery.filter(Response.hero_id == hero.id)
		if criteria:
			basequery = basequery.filter(or_(Response.criteria.like(criteria + "%"), Response.criteria.like("%|" + criteria + "%")))


		if keyphrase == None or keyphrase == "" or keyphrase == " ":
			if basequery.count() > 0:
				return basequery
			else:
				return None

		# Because some of wisp's responses are not named correctly
		if '_' in keyphrase:
			query = basequery.filter(Response.name == keyphrase)
			if query.count() > 0:
				return query

		simple_input = " " + re.sub(r'[^a-z0-9\s]', r'', keyphrase.lower()) + " "

		query = basequery.filter(Response.text_simple == simple_input)
		if query.count() > 0:
			return query

		if not exact:
			query = basequery.filter(Response.text_simple.like("%" + simple_input + "%"))
			if query.count() > 0:
				return query

		return None

	async def get_laugh_response(self, hero=None):
		query = session.query(Response)
		hero = self.lookup_hero(hero)
		if hero is not None:
			query = query.filter(Response.hero_id == hero.id)
		query = query.filter(Response.criteria.like(f"%|HeroChatWheel%"))
		query = query.filter(Response.criteria.like(f"%IsEmoteLaugh%"))
		query = query.order_by(func.random())

		response = query.first()
		if response is None:
			query = session.query(Response)
			query = query.filter(Response.hero_id == hero.id)
			query = query.filter(Response.criteria.like(f"%IsEmoteLaugh%"))
			response = query.first()
		return response

	@commands.command(aliases=["hi"])
	async def hello(self, ctx):
		"""Says hello

		WHAT MORE DO YOU NEED TO KNOW!?!?!? IS 'Says hello' REALLY NOT CLEAR ENOUGH FOR YOU!?!!11?!!?11!!?!??"""
		dota_hellos = [
			"slark_attack_11",
			"kunk_thanks_02",
			"meepo_scepter_06",
			"puck_ability_orb_03",
			"tink_spawn_07",
			"treant_ally_08",
			"wraith_lasthit_02",
			"timb_deny_08",
			"tech_pain_39",
			"meepo_attack_08",
			"slark_lasthit_02"
		]
		dota_response = random.choice(dota_hellos)
		response = session.query(Response).filter(Response.name == dota_response).first()
		logger.info("hello: " + response.name)
		await self.play_response(response, ctx)

	@Audio.play.sub_command(name="chatwheel")
	async def play_chatwheel(self, inter: disnake.CmdInter, text: str):
		"""Plays the given chat wheel sound. Try '/clips chatwheel' to get a list of clips.

		Parameters
		----------
		text: The text shown when the chatwheel is played
		"""
		message = self.get_chatwheel_sound(text, True)
		if message is None:
			raise UserError(f"Couldn't find chat wheel sound '{text}'")

		await self.play_clip(f"dotachatwheel:{message.id}", inter, print=True)
	
	@Audio.clips.sub_command(name="chatwheel")
	async def clips_chatwheel(self, inter: disnake.CmdInter, text: str, page: commands.Range[1, 50] = 1):
		"""Shows a list of chatwheel lines
		
		Parameters
		----------
		text: Part of the text shown when the chatwheel is played. Say "all" to get all chatwheel messages.
		page: Which page of clips to view
		"""
		query = session.query(ChatWheelMessage).filter(ChatWheelMessage.sound.like("/%"))
		if text != "all":
			query = query.filter(ChatWheelMessage.message.ilike(f"%{text}%"))
		clipids = []
		cliptext = []
		for message in query.all():
			clipids.append(f"dotachatwheel:{message.id}")
			text = message.message
			sizelimit = 45
			if len(text) > sizelimit:
				text = text[:sizelimit - 3] + "..."
			cliptext.append(text)
		audio_cog = self.bot.get_cog("Audio")
		await audio_cog.clips_pager(inter, "Dota Chatwheel Lines", clipids, cliptext, page=page)

	@commands.slash_command()
	async def hero(self, inter: disnake.CmdInter, hero: Hero):
		"""Gets information about a specific hero
		
		Parameters
		----------
		hero: The name or id of the hero
		"""
		await inter.response.defer()

		description = ""
		def add_attr(name, base_func, gain_func):
			global description
			result = f"{base_func(hero)} + {gain_func(hero)}"
			if hero.attr_primary == name:
				result = f"**{result}**"
			icon = self.get_emoji(f"attr_{name}")
			return f"{icon} {result}\n"

		description += add_attr("strength", lambda h: h.attr_strength_base, lambda h: h.attr_strength_gain)
		description += add_attr("agility", lambda h: h.attr_agility_base, lambda h: h.attr_agility_gain)
		description += add_attr("intelligence", lambda h: h.attr_intelligence_base, lambda h: h.attr_intelligence_gain)

		embed = disnake.Embed(description=description)

		if hero.color:
			embed.color = disnake.Color(int(hero.color[1:], 16))

		wikiurl = self.get_wiki_url(hero)

		embed.set_author(name=hero.localized_name, icon_url=f"{self.vpkurl}{hero.icon}", url=wikiurl)
		embed.set_thumbnail(url=f"{self.vpkurl}{hero.portrait}")

		base_damage = {
			"strength": hero.attr_strength_base,
			"agility": hero.attr_agility_base,
			"intelligence": hero.attr_intelligence_base
		}[hero.attr_primary]

		attack_stats = (
			f"{self.get_emoji('hero_damage')} {base_damage + hero.attack_damage_min} - {base_damage + hero.attack_damage_max}\n"
			f"{self.get_emoji('hero_attack_rate')} {hero.attack_rate}\n"
			f"{self.get_emoji('hero_attack_range')} {hero.attack_range}\n")
		if not hero.is_melee:
			attack_stats += f"{self.get_emoji('hero_projectile_speed')} {hero.attack_projectile_speed:,}\n"
		embed.add_field(name="Attack", value=attack_stats)

		base_armor = hero.base_armor + round(hero.attr_agility_base / 6.0, 1)
		embed.add_field(name="Defence", value=(
			f"{self.get_emoji('hero_armor')} {base_armor:0.1f}\n"
			f"{self.get_emoji('hero_magic_resist')} {hero.magic_resistance}%\n"))

		embed.add_field(name="Mobility", value=(
			f"{self.get_emoji('hero_speed')} {hero.base_movement}\n"
			f"{self.get_emoji('hero_turn_rate')} {hero.turn_rate}\n"
			f"{self.get_emoji('hero_vision_range')} {hero.vision_day:,} / {hero.vision_night:,}\n"))

		if hero.real_name != '':
			embed.add_field(name="Real Name", value=hero.real_name)

		roles = hero.roles.split("|")
		embed.add_field(name=f"Role{'s' if len(roles) > 1 else ''}", value=', '.join(roles))

		await inter.send(embed=embed)

		query = session.query(Response).filter(Response.hero_id == hero.id).filter(or_(Response.criteria.like("Spawn %"), Response.criteria.like("Spawn%")))
		if query.count() > 0:
			try:
				await self.play_response_query(query, inter)
			except AudioPlayerNotFoundError:
				pass

	@commands.command()
	async def talents(self, ctx, *, hero : str):
		"""Gets the talents of a specific hero

		You can give this command almost any variant of the hero's name, or the hero's id, in the same format as `{cmdpfx}hero`

		**Examples:**
		`{cmdpfx}talents shadow fiend`"""
		hero = self.lookup_hero(hero)
		if not hero:
			raise UserError("That doesn't look like a hero")

		image = await drawdota.draw_hero_talents(hero)
		image = disnake.File(image, f"{hero.name}_talents.png")

		await ctx.send(file=image)


	@commands.command(aliases=["spell"])
	async def ability(self, ctx, *, ability : str):
		"""Gets information about a specific hero ability

		**Examples:**
		`{cmdpfx}ability rocket flare`
		`{cmdpfx}ability laser`
		`{cmdpfx}ability sprout`"""

		ability = self.lookup_ability(ability)

		if ability is None:
			raise UserError("I couldn't find an ability by that name")

		def format_values(values):
			values = values.split(" ")
			return " / ".join(values)

		description = ""

		ability_behavior = OrderedDict([])
		ability_behavior["channelled"] = "Channelled"
		ability_behavior["autocast"] = "Auto-Cast"
		ability_behavior["unit_target"] = "Unit Target"
		ability_behavior["point"] = "Point Target"
		ability_behavior["toggle"] = "Toggle"
		ability_behavior["aura"] = "Aura"
		ability_behavior["passive"] = "Passive"
		ability_behavior["no_target"] = "No Target"

		if ability.behavior:
			behavior = ability.behavior.split("|")
			for key in ability_behavior:
				if key in behavior:
					extra_stuff = ""
					if "aoe" in behavior:
						extra_stuff = f" (AOE)"
					description += f"**Ability:** {ability_behavior[key]}{extra_stuff}\n"
					break

		if ability.damage_type:
			damage_type = ability.damage_type[0].upper() + ability.damage_type[1:]
			description += f"**Damage Type:** {damage_type}\n"

		if ability.spell_immunity:
			spell_immunity = ability.spell_immunity[0].upper() + ability.spell_immunity[1:]
			description += f"**Pierces Spell Immunity:** {spell_immunity}\n"

		if ability.dispellable:
			dispellable = {
				"yes": "Yes",
				"no": "No",
				"yes_strong": "Strong Dispells Only"
			}[ability.dispellable]
			description += f"**Dispellable:** {dispellable}\n"


		if description != "":
			description += "\n"

		description += ability.description

		ability_special = json.loads(ability.ability_special, object_pairs_hook=OrderedDict)
		attribute_additions = [
			{
				"key": "damage",
				"header": "Damage:",
				"value": ability.damage,
				"first": True
			},
			{
				"key": "channel_time",
				"header": "Channel Time:",
				"value": ability.channel_time
			},
			{
				"key": "cast_range",
				"header": "Cast Range:",
				"value": ability.cast_range if ability.cast_range != 0 else None
			},
			{
				"key": "cast_point",
				"header": "Cast Point:",
				"value": ability.cast_point
			}
		]
		for attr in attribute_additions:
			attribute = next((x for x in ability_special if (x.get("header") and format_pascal_case(x.get("header"))) == attr["header"]), None)
			if attribute:
				attribute["first"] = attr.get("first")
				if attribute.get("value", "") == "" and attr["value"] is not None:
					attribute["value"] = attr["value"]
			else:
				if attr["value"] is not None:
					ability_special.append(attr)
		first_attr = next((x for x in ability_special if x.get("first")), None)
		if first_attr:
			ability_special.remove(first_attr)
			ability_special.insert(0, first_attr)

		formatted_attributes = []
		scepter_attributes = []
		shard_attributes = []
		for attribute in ability_special:
			header = attribute.get("header")
			if not header:
				continue
			header = format_pascal_case(header)

			value = attribute["value"]
			footer = attribute.get("footer")
			text = f"**{header}** {format_values(value)}"
			if footer:
				text += f" {footer}"

			if attribute.get("scepter_upgrade") and not ability.scepter_grants:
				scepter_attributes.append(text)
			elif attribute.get("shard_upgrade") and not ability.shard_grants:
				shard_attributes.append(text)
			else:
				formatted_attributes.append(text)

		if formatted_attributes:
			description += "\n\n" + "\n".join(formatted_attributes)

		# talents
		talent_query = query_filter_list(session.query(Talent), Talent.linked_abilities, ability.name)
		talents = talent_query.order_by(Talent.slot).all()
		if len(talents) > 0:
			description += f"\n\n{self.get_emoji('talent_tree')} **Talents:**"
			for talent in talents:
				description += f"\n[Level {talent.level}] {talent.localized_name}"

		# aghs scepter
		if ability.scepter_description:
			if ability.scepter_grants:
				description += f"\n\n{self.get_emoji('aghanims_scepter')} **Granted by Aghanim's Scepter**"
			else:
				description += f"\n\n{self.get_emoji('aghanims_scepter')} __**Upgradable by Aghanim's Scepter**__\n"
				description += f"*{ability.scepter_description}*\n"
				for attribute in scepter_attributes:
					description += f"\n{attribute}"

		# aghs shard
		if ability.shard_description:
			if ability.shard_grants:
				description += f"\n\n{self.get_emoji('aghanims_shard')} **Granted by Aghanim's Shard**"
			else:
				description += f"\n\n{self.get_emoji('aghanims_shard')} __**Upgradable by Aghanim's Shard**__\n"
				description += f"*{ability.shard_description}*\n"
				for attribute in shard_attributes:
					description += f"\n{attribute}"

		embed = disnake.Embed(description=description)

		embed.title = ability.localized_name
		embed.url = self.get_wiki_url(ability)

		embed.set_thumbnail(url=f"{self.vpkurl}{ability.icon}")

		if ability.cooldown and ability.cooldown != "0":
			value = format_values(ability.cooldown)
			if ability.charges:
				value += f" ({ability.charges} Charges)"
			embed.add_field(name="\u200b", value=f"{self.get_emoji('cooldown')} {value}\n")

		if ability.mana_cost and ability.mana_cost != "0":
			embed.add_field(name="\u200b", value=f"{self.get_emoji('mana_cost')} {format_values(ability.mana_cost)}\n")

		if ability.lore and ability.lore != "":
			embed.set_footer(text=ability.lore)

		await ctx.send(embed=embed)

	@commands.command()
	async def item(self, ctx, *, item : str):
		"""Gets information about a specific item

		**Examples:**
		`{cmdpfx}item shadow blade`
		`{cmdpfx}item tango`"""

		item = self.lookup_item(item)

		if item is None:
			raise UserError("I couldn't find an item by that name")

		description = ""

		if item.neutral_tier is not None:
			description += f"**Tier {item.neutral_tier}** Neutral Item\n\n"


		def format_values(values, join_string="/", base_level=None):
			if values is None:
				return None
			values = values.split(" ")
			if base_level and base_level <= len(values):
				values[base_level - 1] = f"**{values[base_level - 1]}**"
			else:
				values = map(lambda v: f"**{v}**", values)
			return join_string.join(values)

		ability_special = json.loads(item.ability_special, object_pairs_hook=OrderedDict)
		for attribute in ability_special:
			header = attribute.get("header")
			if not header:
				continue
			value = attribute["value"]
			footer = attribute.get("footer")
			text = f"{header} {format_values(value, base_level=item.base_level)}"
			if footer:
				text += f" {footer}"
			text += "\n"
			description += text


		if item.description:
			if description != "":
				description += "\n"
			description += item.description
			description += "\n"
		description = re.sub(r"(^|\n)# ([^\n]+)\n", r"\n__**\2**__\n", description)

		def clean_values(values):
			values = values.split(" ")
			return " / ".join(values)

		description += "\n"
		if item.cost and item.cost != "0":
			description += f"{self.get_emoji('gold')} {item.cost:,}\n"
		if item.mana_cost and item.mana_cost != "0":
			description += f"{self.get_emoji('mana_cost')} {clean_values(item.mana_cost)}  "
		if item.cooldown and item.cooldown != "0":
			description += f"{self.get_emoji('cooldown')} {clean_values(item.cooldown)}"

		embed = disnake.Embed(description=description)

		color = drawdota.get_item_color(item)
		if color is not None:
			embed.color = disnake.Color(int(color[1:], 16))


		embed.title = item.localized_name
		embed.url = self.get_wiki_url(item)

		embed.set_thumbnail(url=f"{self.vpkurl}{item.icon}")

		if item.lore and item.lore != "":
			embed.set_footer(text=item.lore)

		await ctx.send(embed=embed)


	@commands.command(aliases=["emoji"])
	async def emoticon(self, ctx, name):
		"""Gets the gif of a dota emoticon

		<a:pup:406270527766790145> <a:stunned:406274986769252353> <a:cocky:406274999951949835>

		**Examples:**
		`{cmdpfx}emoticon pup`
		`{cmdpfx}emoticon stunned`
		`{cmdpfx}emoticon naga_song`"""
		await ctx.channel.trigger_typing()

		emoticon = session.query(Emoticon).filter(Emoticon.name == name).first()

		if not emoticon:
			raise UserError(f"Couldn't find an emoticon with the name '{name}'")

		url = self.vpkurl + emoticon.url

		filetype = "gif" if emoticon.frames > 1 else "png"
		image = disnake.File(await drawdota.create_dota_emoticon(emoticon, url), f"{name}.{filetype}")

		await ctx.send(file=image)

	@commands.command(aliases=["addemoji"])
	async def addemoticon(self, ctx, name):
		"""Adds a dota emoticon as an animated emoji

		This command will add the dota emoticon as an animated emoji to the server. Because it is an animated emoji, only discord nitro users will be able to use it.

		Obviously, this command needs the 'Manage Emoji' permission to be able to work.

		<a:pup:406270527766790145> <a:stunned:406274986769252353> <a:cocky:406274999951949835>

		**Examples:**
		`{cmdpfx}addemoticon pup`
		`{cmdpfx}addemoticon stunned`
		`{cmdpfx}addemoticon naga_song`"""

		emoticon = session.query(Emoticon).filter(Emoticon.name == name).first()

		if not emoticon:
			raise UserError(f"Couldn't find an emoticon with the name '{name}'")

		url = self.vpkurl + emoticon.url
		image = await drawdota.create_dota_emoticon(emoticon, url)
		with open(image, 'rb') as f:
			image = f.read()

		if not ctx.guild:
			raise UserError("You have to be in a server to use this command")

		if not ctx.guild.me.guild_permissions.manage_emojis:
			raise UserError("An admin needs to give me the 'Manage Emojis' permission before I can do that")

		await ctx.guild.create_custom_emoji(name=name, image=image, reason=f"Dota emoji created for {ctx.message.author.name}")

		await ctx.message.add_reaction("✅")

	@commands.command()
	async def lore(self, ctx, *, name=None):
		"""Gets the lore of a hero, ability, or item

		Returns a random piece of lore if no name is specified

		**Examples:**
		`{cmdpfx}lore bristleback`
		`{cmdpfx}lore shadow blade`
		`{cmdpfx}lore venomous gale`"""
		lore_info = {}
		found = False

		if name is None:
			# Randomize!
			names = []
			for item in session.query(Item).filter(Item.lore != ""):
				names.append(item.localized_name)
			for ability in session.query(Ability).filter(Ability.lore != ""):
				names.append(ability.localized_name)
			for hero in session.query(Hero).filter(Hero.bio != ""):
				names.append(hero.localized_name)
			name = random.choice(names)

		item = self.lookup_item(name, False)
		if item:
			found = True
			lore_info = {
				"name": item.localized_name,
				"icon": item.icon,
				"lore": item.lore,
				"object": item
			}

		if not found:
			ability = self.lookup_ability(name, False)
			if ability:
				found = True
				lore_info = {
					"name": ability.localized_name,
					"icon": ability.icon,
					"lore": ability.lore,
					"object": ability
				}

		if not found:
			hero = self.lookup_hero(name)
			if hero:
				found = True
				lore_info = {
					"name": hero.localized_name,
					"icon": hero.portrait,
					"lore": hero.bio,
					"object": hero
				}

		if not found:
			raise UserError("I Couldn't find an ability hero or item by that name")

		if lore_info["lore"] == "":
			raise UserError("There is no in-game lore for that")


		lore_text = lore_info["lore"]
		maxlen = 1950
		if len(lore_text) > maxlen:
			lore_text = lore_text[:maxlen] + "..."
		embed = disnake.Embed(description=lore_text)

		embed.title = lore_info["name"]
		embed.url = self.get_wiki_url(lore_info["object"])

		if lore_info["icon"]:
			embed.set_thumbnail(url=f"{self.vpkurl}{lore_info['icon']}")

		await ctx.send(embed=embed)

	@commands.command(aliases=["aghs", "ags", "aghanims", "scepter", "shard"])
	async def aghanim(self, ctx, *, name):
		"""Gets the aghs upgrade for the given hero or ability

		This command will get the information about shard upgrades AND scepter upgrades.
		If you want just shard or just scepter upgrades, try using `{cmdpfx}scepter` or `{cmdpfx}shard`"""
		only_do_scepter = ctx.invoked_with == "scepter"
		only_do_shard = ctx.invoked_with == "shard"

		abilities = []
		hero = self.lookup_hero(name)
		if hero:
			for ability in hero.abilities:
				if (ability.shard_upgrades or ability.shard_grants) and not only_do_scepter:
					abilities.append(ability)
				elif (ability.scepter_upgrades or ability.scepter_grants) and not only_do_shard:
					abilities.append(ability)

			if len(abilities) == 0:
				raise UserError(f"Couldn't find an aghs upgrade for {hero.localized_name}. Either they don't have one or I just can't find it.")
		else:
			ability = self.lookup_ability(name, True)
			if not ability:
				raise UserError("Couldn't find a hero or ability by that name")
			abilities = [ ability ]

		item_shard = self.lookup_item("aghanim's shard")
		item_scepter = self.lookup_item("aghanim's scepter")
		upgrade_types = [ "scepter", "shard" ]
		if only_do_scepter:
			upgrade_types = [ "scepter" ]
		elif only_do_shard:
			upgrade_types = [ "shard" ]

		for upgrade_type in upgrade_types:
			aghs_item = item_scepter
			icon_url = f"{self.vpkurl}/panorama/images/hud/reborn/aghsstatus_scepter_on_psd.png"
			if upgrade_type == "shard":
				aghs_item = item_shard
				icon_url = f"{self.vpkurl}/panorama/images/hud/reborn/aghsstatus_shard_on_psd.png"
			for ability in abilities:
				description = ability.scepter_description if upgrade_type == "scepter" else ability.shard_description
				is_grantedby = ability.scepter_grants if upgrade_type == "scepter" else ability.shard_grants
				if description != "":
					if is_grantedby:
						description = f"**{description}**\n\n*{ability.description}*"
					else:
						description = f"*{description}*\n"

				ability_special = json.loads(ability.ability_special, object_pairs_hook=OrderedDict)
				formatted_attributes = []
				if upgrade_type == "scepter" and ability.scepter_upgrades and not ability.scepter_grants:
					for attribute in ability_special:
						header = attribute.get("header")
						if not (header and attribute.get("scepter_upgrade")):
							continue
						header = format_pascal_case(header)
						value = attribute["value"]
						footer = attribute.get("footer")
						value = " / ".join(value.split(" "))
						text = f"**{header}** {value}"
						if footer:
							text += f" {footer}"
						if description != "":
							description += "\n"
						description += f"{text}"

				if description == "":
					continue
				embed = disnake.Embed(description=description)
				title = f"{aghs_item.localized_name} ({ability.localized_name})"
				embed.set_author(name=title, icon_url=icon_url)
				embed.set_thumbnail(url=f"{self.vpkurl}{ability.icon}")
				await ctx.send(embed=embed)

	@commands.command(aliases=["recipes", "craft", "crafting"])
	async def recipe(self, ctx, *, item):
		"""Shows the recipes involving this item"""
		item = self.lookup_item(item, True)
		if not item:
			raise UserError("Can't find an item by that name")

		products = query_filter_list(session.query(Item), Item.recipe, item.name).all()
		components = []
		if item.recipe:
			component_names = item.recipe.split("|")
			found_components = session.query(Item).filter(Item.name.in_(component_names)).all()
			for name in component_names:
				for component in found_components:
					if component.name == name:
						components.append(component)
						break


		embed = disnake.Embed()

		embed.description = f"**Total Cost:** {self.get_emoji('gold')} {item.cost}"

		if components:
			value = ""
			for i in components:
				value += f"{i.localized_name} ({self.get_emoji('gold')} {i.cost})\n"
			embed.add_field(name="Created from", value=value)
		if products:
			value = ""
			for i in products:
				value += f"{i.localized_name} ({self.get_emoji('gold')} {i.cost})\n"
			embed.add_field(name="Can be made into", value=value)

		title = item.localized_name
		if len(products) > 1 or (components and products):
			title += " (Recipes)"
		else:
			title += " (Recipe)"

		embed.title = title
		embed.url = self.get_wiki_url(item)

		color = drawdota.get_item_color(item)
		if color is not None:
			embed.color = disnake.Color(int(color[1:], 16))

		image = disnake.File(await drawdota.draw_itemrecipe(item, components, products), "recipe.png")
		embed.set_image(url=f"attachment://{image.filename}")

		await ctx.send(embed=embed, file=image)



	@commands.command(aliases=["fuse", "fuze", "fuzeheroes"])
	async def fuseheroes(self, ctx, *, heroes=None):
		"""See what would happen if you fused two heroes together

		If no heroes are given, two will be chosen at random

		**Example:**
		`{cmdpfx}fuseheroes axe chen`"""
		await ctx.channel.trigger_typing()
		if heroes is None:
			heroes = session.query(Hero).order_by(func.random()).limit(2).all()
			heroes = " ".join(map(lambda h: h.localized_name, heroes))

		words = heroes.split(" ")

		hero1 = None
		hero2 = None
		for i in range(1, len(words)):
			hero1 = self.lookup_hero(" ".join(words[:i]))
			hero2 = self.lookup_hero(" ".join(words[i:]))
			if hero1 and hero2:
				break

		if not (hero1 and hero2):
			raise UserError("That doesn't look like two distinct heroes")
		if hero1.id == hero2.id:
			raise UserError("Fusing something with itself sounds boring")

		def combine_words(word1, word2):
			middle1 = len(word1) - (len(word1) // 2)
			middle2 = len(word2) - (len(word2) // 2)
			return word1[:middle1] + word2[middle2:]

		name1 = hero1.localized_name
		name2 = hero2.localized_name
		if " " not in name1 and " " not in name2:
			hero_name = combine_words(name1, name2)
		if " " in name1 and " " not in name2:
			hero_name = name1.split(" ")[0] + " " + name2
		if " " not in name1 and " " in name2:
			hero_name = name1 + " " + name2.split(" ")[-1]
		if " " in name1 and " " in name2:
			hero_name = name1.split(" ")[0] + " " + name2.split(" ")[-1]
			if hero_name == name1 or hero_name == name2:
				hero_name = combine_words(name1.split(" ")[0], name2.split(" ")[0]) + " " + name2.split(" ")[-1]
			if hero_name == name1 or hero_name == name2:
				hero_name = name1.split(" ")[0] + " " + combine_words(name1.split(" ")[-1], name2.split(" ")[-1])


		embed = disnake.Embed()

		embed.title = hero_name

		emoji1 = self.get_emoji(f"dota_hero_{hero1.name}")
		emoji2 = self.get_emoji(f"dota_hero_{hero2.name}")

		embed.description = f"{emoji1} + {emoji2}"

		color1 = imagetools.Color(hero1.color)
		color2 = imagetools.Color(hero2.color)
		color = color1.blend(color2)
		embed.color = disnake.Color(color.integer)

		image = disnake.File(await drawdota.fuse_hero_images(hero1, hero2), "hero.png")
		embed.set_thumbnail(url=f"attachment://{image.filename}")

		await ctx.send(embed=embed, file=image)


	@commands.command()
	async def courage(self, ctx, *, hero = None):
		"""Generates a challenge build

		Creates a challenge build with a random (or given) hero and a random set of items

		**Examples:**
		`{cmdpfx}courage`
		`{cmdpfx}courage shadow fiend`"""

		all_boots = query_filter_list(session.query(Item), Item.recipe, "item_boots").all()

		random.seed(datetime.datetime.now())
		items = session.query(Item) \
			.filter(~Item.localized_name.contains("Recipe")) \
			.filter(~Item.localized_name.contains("Boots")) \
			.filter(Item.recipe != None) \
			.filter(Item.icon != None) \
			.filter(Item.cost > 2000) \
			.order_by(func.random()) \
			.limit(5) \
			.all()
		items.append(random.choice(all_boots))
		random.shuffle(items)

		item_ids = []
		for item in items:
			item_ids.append(item.id)
		if hero:
			hero_id = self.lookup_hero_id(hero)
			if not hero_id:
				raise UserError(f"Couldn't a hero called '{hero}'")
		else:
			hero_id = session.query(Hero).order_by(func.random()).first().id

		logger.info(item_ids)

		image = disnake.File(await drawdota.draw_courage(hero_id, item_ids), "courage.png")
		await ctx.send(file=image)


	@commands.command(aliases=["neutrals", "neutraltier"])
	async def neutralitems(self, ctx, *, tier = None):
		"""Displays all of the neutral items

		If a tier is specified, display the items in that tier, along with their names

		`{cmdpfx}neutralitems`
		`{cmdpfx}neutralitems tier 5`
		`{cmdpfx}neutralitems 3`"""

		if tier is not None:
			tier = tier.lower().replace("tier", "").replace("t", "").strip()
			if not tier.isdigit():
				raise UserError("Please specify a tier like 'tier 5'")
			tier = int(tier)
			if tier < 1 or tier > 5:
				raise UserError("Please specify a tier between 1 and 5")

		embed = disnake.Embed()

		title = "Neutral Items"
		if tier is not None:
			title = f"Tier {tier} Neutral Items"
		embed.title = title
		embed.url = "https://dota2.gamepedia.com/Neutral_Items"

		all_neutral_items = session.query(Item).filter(Item.neutral_tier != None).filter(Item.recipe == None).order_by(Item.localized_name).all()
		image = disnake.File(await drawdota.draw_neutralitems(tier, all_neutral_items), "neutralitems.png")
		embed.set_image(url=f"attachment://{image.filename}")
		if tier is not None:
			tier_color = drawdota.neutral_tier_colors[str(tier)]
			embed.color = disnake.Color(int(tier_color[1:], 16))

		if tier is None:
			embed.set_footer(text="Also try: ?neutralitems tier 4")
		await ctx.send(embed=embed, file=image)

	@commands.command(aliases=["startingstats", "tradingstats", "lvlstats", "lvledstats"])
	async def leveledstats(self, ctx, *, hero : str):
		"""Gets the stats for a hero at the specified level

		If no level is specified, get the stats for the hero at level 1

		**Examples:**
		`{cmdpfx}leveledstats tinker`
		`{cmdpfx}leveledstats shaker lvl 2`
		`{cmdpfx}leveledstats level 28 shaman`"""
		lvl_regex = r"(?:(max) (?:lvl|level)|(?:lvl|level)? ?(\d+))"
		match = re.search(lvl_regex, hero, re.IGNORECASE)
		level = 1
		if match:
			if match.group(1):
				level = 30
			else:
				level = int(match.group(2))
			if level < 1 or level > 30:
				raise UserError("Please enter a level between 1 and 30")
			hero = re.sub(lvl_regex, "", hero)

		hero = self.lookup_hero(hero)
		if not hero:
			raise UserError("That doesn't look like a hero")

		stat_category = next((c for c in self.hero_stat_categories if c["section"] == "Combat Stats"), None)["stats"]

		description = ""
		hero_stats = next((h for h in self.leveled_hero_stats[level] if h["id"] == hero.id), None)

		for stat in stat_category:
			name = stat["name"]
			value = hero_stats[stat["stat"]]
			if stat.get("display") == "resistance_percentage":
				value = 100 * (1 - value)
			if stat.get("display") == "int":
				value = round(value)
			value = f"{value:.2f}"
			value = re.sub("\.0+$", "", value)
			if stat.get("display") == "resistance_percentage":
				value += "%"
			description += f"\n{name}: **{value}**"

		embed = disnake.Embed(description=description)

		title = f"Level {level} {hero.localized_name}"
		embed.set_author(name=title, icon_url=f"{self.vpkurl}{hero.icon}")
		embed.set_thumbnail(url=f"{self.vpkurl}{hero.portrait}")
		if hero.color:
			embed.color = disnake.Color(int(hero.color[1:], 16))
		embed.set_footer(text="The stats shown above do not account for talents, passives, or items")

		await ctx.send(embed=embed)

	@commands.command(aliases=["statstable", "stattable", "heroestable", "leveledstatstable", "besthero", "bestheroes"])
	async def herotable(self, ctx, *, table_args : HeroStatsTableArgs):
		"""Displays a sorted table of heroes and their stats

		Displays a table with computed hero stats showing which heroes have the highest values for the specified stat. To see the list of possible stats, try the `{cmdpfx}leveledstats` command

		**Examples:**
		`{cmdpfx}herotable dps`
		`{cmdpfx}herotable health lvl 30`
		`{cmdpfx}herotable attack speed level 21 descending`
		"""
		if table_args.stat is None:
			raise UserError(f"Please select a stat to sort by. For a list of stats, see `{self.cmdpfx(ctx)}leveledstats`")
		if table_args.hero_level < 1 or table_args.hero_level > 30:
			raise UserError("Please select a hero level between 1 and 30")
		if table_args.hero_count < 2 or table_args.hero_count > 40:
			raise UserError("Please select a hero count between 2 and 40")

		embed = disnake.Embed()

		image = disnake.File(await drawdota.draw_herostatstable(table_args, self.hero_stat_categories, self.leveled_hero_stats), "herotable.png")
		embed.set_image(url=f"attachment://{image.filename}")
		embed.set_footer(text="The stats shown above do not account for talents, passives, or items")

		await ctx.send(embed=embed, file=image)

	@commands.command(aliases=["spells"])
	async def abilities(self, ctx, *, hero):
		"""Shows all of the abilities/spells for that hero"""
		hero = self.lookup_hero(hero)
		if not hero:
			raise UserError("That doesn't look like a hero")

		abilities = []
		for ability in list(filter(lambda a: a.slot is not None, hero.abilities)):
			if not hero.id == 74: # invoker
				if "hidden" in (ability.behavior or "") and not (ability.shard_grants or ability.scepter_grants):
					continue
			abilities.append(ability)

		embed = disnake.Embed()

		embed.title = hero.localized_name
		embed.url = self.get_wiki_url(hero)

		image = disnake.File(await drawdota.draw_heroabilities(abilities), "abilities.png")
		embed.set_image(url=f"attachment://{image.filename}")

		embed.color = disnake.Color(int(hero.color[1:], 16))

		await ctx.send(embed=embed, file=image)


	@commands.command(aliases = ["rss"])
	async def blog(self,ctx):
		""" Pulls the newest blog post for Dota 2"""
		await ctx.send("Sorry, Valve broke this for now.")
		return # return cuz valve broke it
		feed = await httpgetter.get(r'https://blog.dota2.com/feed', return_type="text")
		blog = feedparser.parse(feed)
		title = "Dota 2 Blog"
		embed = rsstools.create_embed(title, blog.entries[0])
		await ctx.send(embed = embed)

	@tasks.loop(minutes=5)
	async def check_dota_blog(self):
		feed = await httpgetter.get(r'https://blog.dota2.com/feed', return_type="text")
		blog = feedparser.parse(feed)
		title = "Dota 2 Blog"

		updated = rsstools.is_new_blog(blog.entries[0])
		if not updated: #if its not updated, stop here
			return

		embed = rsstools.create_embed(title, blog.entries[0]) #generate embed

		##next section copies code in check_dota_patch in general cogs
		messageables = []
		#find channels to post in
		guildinfos = botdata.guildinfo_list()
		for guildinfo in guildinfos:
			if guildinfo.dotablogchannel is not None:
				channel = self.bot.get_channel(guildinfo.dotablogchannel)
				if channel is not None:
					messageables.append(channel)
				else:
					logger.info(f"couldn't find channel {guildinfo.dotablogchannel} when announcing dota blog")

		#find users
		userinfos = botdata.userinfo_list()
		for userinfo in userinfos:
			if userinfo.dmdotablog:
				user = self.bot.get_user(userinfo.discord)
				if user is not None:
					messageables.append(user)
				else:
					logger.info(f"couldn't find user {userinfo.discord} when announcing dota blog")

		#bundle tasks and execute
		tasks = []
		for messageable in messageables:
			tasks.append(messageable.send(embed=embed))

		bundler = AsyncBundler(tasks)
		await bundler.wait()


def setup(bot):
	bot.add_cog(Dotabase(bot))
