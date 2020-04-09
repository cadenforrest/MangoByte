# MangoByte<img align="right" src="/resource/images/readme/mangobyte.png"/>

[![Servers](https://img.shields.io/badge/dynamic/json.svg?label=servers&url=http%3A%2F%2Fdillerm.io%2Fshieldstats%2Fmangobyte.json&query=%24.servers&colorB=#4c1)](https://discordapp.com/oauth2/authorize?permissions=60480&scope=bot&client_id=213476188037971968)
[![Registered Users](https://img.shields.io/badge/dynamic/json.svg?label=registered%20users&url=http%3A%2F%2Fdillerm.io%2Fshieldstats%2Fmangobyte.json&query=%24.registered_users&colorB=#4c1)](https://discordapp.com/oauth2/authorize?permissions=60480&scope=bot&client_id=213476188037971968)

- [Add the bot to your server](https://discordapp.com/oauth2/authorize?permissions=60480&scope=bot&client_id=213476188037971968)
- [Join the MangoByte help server](https://discord.gg/d6WWHxx)

A discord bot that provides the ability to play audio clips, play dota responses, answer questions, randomly react to messages, and a large number of other actions. I'm using the [discord.py](https://github.com/Rapptz/discord.py) python wrapper for the [Discord API](https://discordapp.com/developers). I'm also making use of [dotabase](https://github.com/mdiller/dotabase), which is an open source repository (created by yours truly) containing data about the game [Dota 2](http://www.dota2.com).

## Commands

<!-- COMMANDS_START -->
Mangobyte currently has 79 commands, separated into 8 categories

#### General
Basic and admin commands

```
?ask             | Answers any question you might have                        
?botstats        | Displays some bot statistics                               
?changelog       | Gets a rough changelog for mangobyte                       
?choose          | Randomly chooses one of the given options                  
?docs            | Shows the documentation for the given topic                
?donate          | Posts the donation information                             
?echo            | Echo...                                                    
?help            | Shows this message                                         
?info            | Prints info about mangobyte                                
?insult          | Gets a nice insult for ya                                  
?invite          | Prints the invite link                                     
?lasagna         | A baked Italian dish                                       
?ping            | Pongs a number of times(within reason)                     
?random_number   | Gets a random number between the minimum and maximum       
?reddit          | Displays a formatted reddit post                           
?restget         | Gets a json response from a rest api and returns it        
?scramble        | Scrambles the insides of words                             
?showerthought   | Gets a top post from r/ShowerThoughts                      
?userconfig      | Configures the bot's user-specific settings                
?wiki            | Looks up a thing on wikipedia                              
```

#### Audio
For playing audio in a voice channel

```
?clipinfo        | Gets information and a file for the given clip             
?clips           | Lists the local audio clips available for the play command 
?later           | Tells you how much later it is                             
?play            | Plays an audio clip                                        
?playurl         | Plays an mp3 file at a url                                 
?replay          | Replays the last played clip                               
?smarttts        | Automatically find the best fit for the tts given          
?stop            | Stops the currently playing audio                          
?tts             | Like echo but for people who can't read                    
?ttsclip         | Tries to text-to-speech the given clip                     
```

#### Dotabase
Dota hero responses and info

```
?ability         | Gets information about a specific hero ability             
?addemoticon     | Adds a dota emoticon as an animated emoji                  
?chatwheel       | Plays the given chat wheel sound                           
?courage         | Generates a challenge build                                
?dota            | Plays a dota response                                      
?emoticon        | Gets the gif of a dota emoticon                            
?fuseheroes      | See what would happen if you fused two heroes together     
?hello           | Says hello                                                 
?hero            | Gets information about a specific hero                     
?herotable       | Displays a sorted table of heroes and their stats          
?inthebag        | Proclaims that 'IT' (whatever it is) is in the bag         
?item            | Gets information about a specific item                     
?leveledstats    | Gets the stats for a hero at the specified level           
?lol             | WOW I WONDER WAT THIS DOES                                 
?lore            | Gets the lore of a hero, ability, or item                  
?neutralitems    | Displays all of the neutral items                          
?no              | Nopes.                                                     
?talents         | Gets the talents of a specific hero                        
?thanks          | Gives thanks                                               
?yes             | Oooooh ya.                                                 
```

#### DotaStats
Dota player and match stats

```
?dotagif         | Creates a gif of a specific part of a dota match           
?friendstats     | Statistics of games played with a friend                   
?herostats       | Gets your stats for a hero                                 
?laning          | Creates gif of the laning stage with a caption             
?lastmatch       | Gets info about the player's last dota game                
?lastmatchstory  | Tells the story of the player's last match                 
?match           | Gets a summary of the dota match with the given id         
?matches         | Gets a list of your matches                                
?matchstory      | Tells the story of the match                               
?opendota        | Queries the opendota api                                   
?parse           | Requests that OpenDota parses a match                      
?playerstats     | Gets stats from the player's last 20 parsed games          
?profile         | Displays information about the player's dota profile       
?rolesgraph      | Gets a graph displaying the player's hero roles            
?whoishere       | Shows what discord users are which steam users             
```

#### Pokemon
Pokemon related commands

```
?pokecry         | Plays the pokemon's sound effect                           
?pokedex         | Looks up information about the indicated pokemon           
?shiny           | Gets the shiny version of this pokemon                     
```

#### Artifact
Artifact related commands

```
?card            | Displays info about the artifact card                      
?deck            | Displays the card list for the given deck                  
?updateartifact  | Updates all the artifact card data                         
```

#### Admin
Commands to help manage mangobyte on your server/guild

```
?botban          | Bans the user from using commands                          
?botunban        | Unbans the user, allowing them to use commands             
?config          | Configures the bot's settings for this server              
?disablecommand  | Disabled the specified command or command category         
?enablecommand   | Re-enables the specified command or command category       
?resummon        | Re-summons the bot to the voice channel                    
?summon          | Summons the bot to the voice channel                       
?unsummon        | Removes the bot from the voice channel                     
```

#### Owner
Owner commands

```
```

<!-- COMMANDS_END -->

## Examples

Example of a gif you can create with `?laning` or `?dotagif`:

![DotaGif Command](/resource/images/readme/dotagif.gif)

Example of `?lastgame` command:

![Lastgame Command](/resource/images/readme/lastgame.gif)

This is the long list of all of the commands. You can get this from `?help all`

![Commands List](/resource/images/readme/help_all.png)

## Installation

I would recommend simply inviting mangobyte to your server via the [Invite Link](https://discordapp.com/oauth2/authorize?permissions=60480&scope=bot&client_id=213476188037971968), but if you want to contribute to mangobyte or just like running things, the following is how you can install and run your own instance of mangobyte.

Before installing and running your own instance of mangobyte, you will first need to install the following:

* Python 3.6
* Pip
* Dependencies: `python3.6 -m pip install -r requirements.txt`
* [ffmpeg](https://ffmpeg.org) (the tool used for playing audio)
* [gifsicle](https://www.lcdf.org/gifsicle/) (the tool used for creating gifs)

If you run `python3.6 mangobyte.py`, you will probably get an error message because the bot token isn't set. You'll have to [create a bot account](https://twentysix26.github.io/Red-Docs/red_guide_bot_accounts/) through discord in order to get one of these tokens. Note that the above link is for a different discord bot, and so the "Logging in with a token" section does not apply here. Now that you have a bot account, set the `token` field in the `settings.json` file to your new bot's token. After you have done this, and have invited your bot to your server, don't forget to add the ID of the voice channel you want to connect it to in the `defaultvoice` field in the `settings.json` file.

You should now be done! You can run mangobyte by calling `python3.6 mangobyte.py`, and you should probably set up a virtual environment so that nothing bad has a chance of happening.

### Example settings.json file

```json
{
	"token": "<token here>",
	"error_logging": false,
	"debug": false
}
```
For explanation of each option, see the comments on the properties in [settings.py](cogs/utils/settings.py)
