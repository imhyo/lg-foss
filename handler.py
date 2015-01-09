import os
import datetime
import jinja2
import webapp2
import logging

from google.appengine.api import users
from apiclient.discovery import build
from oauth2client.appengine import OAuth2Decorator

import settings


''' Jinja is a templating language for Python.
Using Jinja, Python code can be embedded into the html file to dynamically construct
html contents.
JINJA_ENVIRONMENT is used to request displaying Jina-based html file.
''' 
JINJA_ENVIRONMENT = jinja2.Environment(
	loader = jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'views')),
	extensions = ['jinja2.ext.autoescape'],
	autoescape = True)

''' decorator is a variable used to request the OAuth2 authentication.
This is used to request calendar events from Google Calendar Service.
'''
decorator = OAuth2Decorator(
	client_id=settings.CLIENT_ID,
	client_secret=settings.CLIENT_SECRET,
	scope=settings.SCOPE)

service = build('calendar', 'v3')


def showError(self, message):
	template_values = {
		'message': message
	}
	template = JINJA_ENVIRONMENT.get_template('error.html')
	self.response.write(template.render(template_values))

	
def showWarning(self, message):
	template_values = {
		'message': message
	}
	template = JINJA_ENVIRONMENT.get_template('index.html')
	self.response.write(template.render(template_values))


""" This is the decorator function which is called just before the function which
has '@auth_required' just before the function definition.
This checks if the current user is in settings.USERS list. """
def auth_required(handler):
	def check_login(self, *args, **kwargs):
		nickname = users.get_current_user().nickname()
		if nickname not in settings.USERS:
			showError(self, 'You don\'t have permission to this site. Please ask the administrator.')
		else:
			return handler(self, *args, **kwargs)

	return check_login

	
""" Handler for the '/' page """	
class MainPage(webapp2.RequestHandler):
	@auth_required
	def get(self):
		self.showDashboard()
		
	@auth_required
	def post(self):
		logging.debug("Post")
		self.showDashboard()
	
	""" This function shows the dashboard which shows the actual working hour / official working hour for each week of the year,
	which is the main feature of this application. """
	def showDashboard(self):
		user = users.get_current_user()
		nickname = self.request.get('user')
		year_str = self.request.get('year')
		if not year_str:
			year = datetime.date.today().year
		else:
			year = int(year_str)
		
		if year < 1900 or year > 9999:
			showError(self, 'Year should be between 1900 and 9999.')
			return

		if not nickname:
			nickname = user.nickname()
		
		# Get the information from the Google Calendar
		week_calendar = self.getCalendar(nickname, year)
		template_values = {
			'calendar': week_calendar,
			'year': year
		}
		
		template = JINJA_ENVIRONMENT.get_template('index.html')
		self.response.write(template.render(template_values))

	# This function get calendar events of the 'year'
	@decorator.oauth_required
	def getEvents(self, year):
		http = decorator.http()
		timeMin = str(year) + '-01-01T00:00:00Z'
		timeMax = str(year + 1) + '-01-01T00:00:00Z'
		request = service.events().list(calendarId = settings.CALENDAR_ID, timeMin = timeMin, timeMax = timeMax)
		events = request.execute(http=http)
		return events
	
	# REST request to Google Calendar doesn't work when the app is runnig in the AppEngine SDK environment.
	# This function is the stub function which is used to test this app without deploying to the server.
	# This function returns fake 'events' similar to the events retrieved from Google Calendar.
	def getEvents2(self, year):
		events = {'items': [
				{'summary': 'holiday', 'creator': {'email': 'hyojun.im@gmail.com'}, 'start': {'date': '2015-01-01'}, 'end': {'date': '2015-01-01'}},
				{'summary': 'holiday', 'creator': {'email': 'hyojun.im@gmail.com'}, 'start': {'date': '2015-01-07'}, 'end': {'date': '2015-01-07'}},
				{'summary': 'leave', 'creator': {'email': 'test@gmail.com'}, 'start': {'date': '2015-01-08'}, 'end': {'date': '2015-01-07'}},
				{'summary': 'leave', 'creator': {'email': 'hyojun.im@gmail.com'}, 'start': {'date': '2015-01-02'}, 'end': {'date': '2015-01-07'}},
				{'summary': 'work', 'creator': {'email': 'test@gmail.com'}, 'start': {'dateTime': '2015-01-02T09:00:00Z'}, 'end': {'dateTime': '2015-01-02T17:00:00Z'}},
				{'summary': 'work', 'creator': {'email': 'test@gmail.com'}, 'start': {'dateTime': '2015-01-06T11:00:00Z'}, 'end': {'dateTime': '2015-01-06T18:00:00Z'}},
				{'summary': 'work', 'creator': {'email': 'test@gmail.com'}, 'start': {'dateTime': '2015-01-09T09:00:00Z'}, 'end': {'dateTime': '2015-01-09T15:00:00Z'}},
				{'summary': 'holiday', 'creator': {'email': 'test@gmail.com'}, 'start': {'date': '2015-02-18'}, 'end': {'date': '2015-02-18'}},
			]}
		return events
		
	# This function gets Google Calendar Events and analyze them to construct week_calendar data structure
	def getCalendar(self, nickname, year):
		holiday_calendar = self.initHolidayCalendar()
		week_calendar = self.initWeekCalendar(year)
		
		# If the nickname is 'test', then use the fake events instead of requesting Google Calendar Service
		# Because requesting to Google Calendar doesn't work when this app is running in the AppEngine SDK environment
		if nickname == 'test':
			events = self.getEvents2(year)
		else:
			events = self.getEvents(year)
		
		while 1:
			if 'items' not in events:
				break

			items = events['items']
			
			# Iterate on all the events returned from Google Calendar
			for i in range(len(items)):
			
				# Retrieve some relevant values from the event for easy access to those values later in this function
				summary = items[i]['summary']		# Summary (Title) of the event
				if 'location' in items[i]:			# Location of the event
					location = items[i]['location']	
				else:
					location = ''
				start = items[i]['start']			# start time (or date) of the event
				end = items[i]['end']				# end time (or date) of the event
				creator = items[i]['creator']		# Creator of the event
				
				""" If the event is all-day event, it can fall into the following three cases
				1. Holiday: The location (or summary) of the event will be 'holiday'
				2. Full-day leave: The creator is on (full-day) leave at that day
				3. Haf-day leave: The creator is on (half-day) leave at that day
				
				This loop checks if the all-day event falls into the above three cases,
				and then marks the element of the holiday_calendar array.
				The element of the holiday_calendar array can have three values:
				0: It is not a holiday (Default)
				1: The user is on half-day leave
				2: It is the holiday or the user is on full-day leave
				
				It also updates the week_calendar array.
				If it is the holiday or full-day leave, then the working hour of that week should be decreased by 8.
				If it is the half-day leave, then the workiing hour of that week should be decreased by 4.
				"""
				if 'date' in start:		# Only all-day events will have 'date' field. (Other events will have 'dateTime' field instead.)
					month = int(start['date'][5:7])
					day = int(start['date'][8:10])
					
					# type 0: weekday, type 1: half-day leave type 2: holiday or full-day leave
					type = 0
					# If the event was created by the current user
					if 'email' in creator and creator['email'] == (nickname + "@gmail.com"):
						# If the location (or summary) is 'half', it means it is the half-day leave
						if summary == 'half' or location == 'half':
							type = 1
						# Otherwise, it means it is the full-day leave
						else:
							type = 2
					# If the event was not created by another user, and if the location (or summary) is 'holiday'
					elif summary == 'holiday' or location == 'holiday':
						type = 2
					
					# Update the holiday_calendar and week_calendar accordingly
					date = datetime.date(year, month, day)
					w = self.getWeekOfYear(year, date)
					if w >= 0 and w < len(week_calendar):
						if holiday_calendar[month][day] == 0:			# If the day was a weekday previously,
							week_calendar[w][3] -= type * 4		# then we have to decrease the working hours for that week
							holiday_calendar[month][day] = type	# and also have to mark it as the holiday.
						elif holiday_calendar[month][day] == 1 and type == 2:	# If the day was a half-day leave and current event shows that it is holiday or full-day leave,
							week_calendar[w][3] -= 4			# then we have to decrease the working hours by 4 for that week
							holiday_calendar[month][day] = type	# and also have to mark it as the half-day leave
				
				# If the event is not a full-day event and the creator is the current user, then we have to update the week_calendar accordingly
				elif ('email' in creator) and (creator['email'] == (nickname + '@gmail.com')):
					sdt = self.getDateTimeFromISO(start['dateTime'])
					edt = self.getDateTimeFromISO(end['dateTime'])
					timedelta = edt - sdt
					sd = sdt.date()
					w = self.getWeekOfYear(year, sd)
					if w >= 0 and w < len(week_calendar):
						week_calendar[w][2] += timedelta.total_seconds() / 3600.0	# Increase the actual working hour for that week (by unit of hour)
						
			""" When there are too many events in Google Calendar, then Google Calendar service will send the
			'nextPageToken' field. We should ask REST request again with the 'pageToken' field. """
			if 'nextPageToken' in events:
				pageToken = events['nextPageToken']
				request = service.events().list(calendarId = settings.CALENDAR_ID, timeMin = timeMin, timeMax = timeMax, pageToken = pageToken)
				events = request.execute(http=http)
				continue
			break
			
		self.roundWorkingHours(week_calendar)
		return week_calendar

	def initHolidayCalendar(self):
		holiday_calendar = range(12)
		for i in range(12):
			holiday_calendar[i] = range(31)
			for j in range(31):
				holiday_calendar[i][j] = 0
		
		return holiday_calendar


	def initWeekCalendar(self, year):
		week_calendar = range(54)
		one_day = datetime.timedelta(1)
		today = datetime.date.today()
		date = datetime.date(year, 1, 1)
		end_date = datetime.date(year, 12, 31)
		
		for i in range(54):
			week_calendar[i] = [datetime.date(year, 1, 1), datetime.date(year, 12, 31), 0.0, 0]
		w = 0

		while date.year == year and date <= today:
			if date.weekday() == 0:
				week_calendar[w][0] = date
	
			if date.weekday() <= 4:
				week_calendar[w][3] += 8
	
			if date.weekday() == 6:
				week_calendar[w][1] = date
				w += 1
				
			date += one_day
	
		if date.weekday() == 0:
			w -= 1
		else:
			date -= one_day
			week_calendar[w][1] = date
			
		return week_calendar[0:w+1]
		
	''' This converts ISO formatted datetime string to datetime data structure.
	Please refer to RFC3339 for the format.
	example: 2015-01-01T09:00:00Z (Jan 1, 2015, 9 am)
	         2015-01-01T09:00:00+09:00 (Jan 1, 2015, 9am, GMT+9 time)
	'''
	def getDateTimeFromISO(self, str):
		year = int(str[0:4])
		month = int(str[5:7])
		day = int(str[8:10])
		hour = int(str[11:13])
		minute = int(str[14:16])
		second = int(str[17:19])
		
		dt = datetime.datetime(year, month, day, hour, minute, second)
		return dt
		

	''' This function rounds up the calculated working hours for user-friendly displaying.
	(ex. 27.134 --> 27.1)
	'''
	def roundWorkingHours(self, week_calendar):
		for week in week_calendar:
			week[2] = round(week[2], 1)


	# This function gets the week of year for the given date
	def getWeekOfYear(self, year, date):
		new_year = datetime.date(year, 1, 1)
		monday = new_year - datetime.timedelta(1) * new_year.weekday()
		t = date - monday
		return (t.days/7)
		


class Logout(webapp2.RequestHandler):
	def get(self):
		logout_url = users.create_logout_url('/')
		self.redirect(logout_url)


application = webapp2.WSGIApplication([
	('/', MainPage),
	('/logout', Logout),
	(decorator.callback_path, decorator.callback_handler()),
], debug=True)
