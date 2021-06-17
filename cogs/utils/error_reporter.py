import os
import traceback
from cogs.utils.helpers import *
from cogs.utils.loggingdb import LoggingDb

loggingdb = LoggingDb(resource("loggingdb.db"))
error_file = "errors.json"

async def report_error(message, error, skip_lines=2):
	if os.path.isfile(error_file):
		error_list = read_json(error_file)
	else:
		error_list = []

	try:
		raise error.original
	except:
		trace = traceback.format_exc().replace("\"", "'").split("\n")
		if skip_lines > 0 and len(trace) >= (2 + skip_lines):
			del trace[1:(skip_lines + 1)]
		trace = [x for x in trace if x] # removes empty lines

	trace_string = "\n".join(trace)

	await loggingdb.insert_error(message, error, trace_string)

	print(f"\nError on: {message.clean_content}\n{trace_string}\n")
	return trace_string