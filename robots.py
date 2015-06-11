#! /usr/bin/python
# -*- coding: utf8 -*-

from pyvirtualdisplay import Display

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

import difflib
import hashlib
import json
import os
import re
import sys
import time
import traceback
import urllib
import urllib2
import tempfile
import imghdr
import stat
import tempfile
import shutil
import subprocess
import uuid
import zlib
import argparse

import mandrill

import menu

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'google'))

try:
	import httplib2
	from googleapiclient import discovery
	from oauth2client import client
	from oauth2client import file
	from oauth2client import tools
	from oauth2client.client import SignedJwtAssertionCredentials
except ImportError, e:
	print "*** GooglePlay libraries not installed! ***"

def _XPathEscape(xpath, expr, new_str):
	sub_res = re.sub(expr, ", {}, ".format(new_str), xpath)
	sub_res = re.sub(r"^, ", '', sub_res)
	return re.sub(r", $", '', sub_res)

def XPathEscape(xpath):
	sub_res = _XPathEscape(xpath, r"'", "\"'\"")
	sub_res = _XPathEscape(sub_res, r"\[", "[")
	sub_res = _XPathEscape(sub_res, r"\]", "]")
	sub_res = _XPathEscape(sub_res, r"\+", "+")
	sub_res = _XPathEscape(sub_res, r"\\", "\\")
	sub_res = _XPathEscape(sub_res, r"/", "/")
	sub_res = _XPathEscape(sub_res, r"\@", "@")
	sub_res = _XPathEscape(sub_res, r"\.", ".")
	sub_res = _XPathEscape(sub_res, r"\,", ",")

	res = ''
	for s in sub_res.split(", "):
		if res == '':
			if s == '"\'"':
				res = s;
			else:
				res = re.sub("\"", ", '\"', ", s);
		else:
			if s == '"\'"':
				res = res + ", " + s
			else:
				res = res + ", " + re.sub("\"", ", '\"', ", s);

	res = re.sub(r"^, ", '', res)
	res = re.sub(r", $", '', res)
	res = re.sub(r"(?:, ){2}", ', ', res)

	sub_res = res

	res = ''
	for s in sub_res.split(", "):
		if res == '':
			if s == '"\'"' or s == "'\"'":
				res = s
			else:
				res = "'" + s + "'"
		else:
			if s == '"\'"' or s == "'\"'":
				res = res + ", " + s
			else:
				res = res + ", " + "'" + s + "'"

	return str('concat(' + str(res.encode('utf-8')) + ", '')".encode('utf-8'))

def Die(msg):
	print(msg)
	sys.exit(1)

def override(interface_class):
	def wrap(method):
		assert(method.__name__ in dir(interface_class))
		return method
	return wrap

def RunXvfb():
	pid = os.spawnvpe(os.P_NOWAIT, 'Xvfb', [ 'Xvfb', ':10', '-ac', '-screen', '0', '1024x768x24' ], os.environ)
	with open('./xvfb.pid', 'w') as f:
				f.write('{}'.format(pid))
				f.close()
	time.sleep(5);
	return pid

class DriverConnector(object):
	def __call__(self):
		return webdriver.Remote(command_executor='http://srv.appnow.com:4444/wd/hub', desired_capabilities=DesiredCapabilities.CHROME)

class DriverConnectorAWS(object):
	def __call__(self):
		pid = None

		if os.path.isfile('./xvfb.pid'):
			try:
				with open('./xvfb.pid', 'r') as f:
					pid = int(f.read())
					f.close()
			except Exception, e:
				pid = None

		#if pid and not IsProcessAlive(pid):
		#	RunXvfb()
		#elif not pid:
		#	RunXvfb()

		display = Display(visible=0, size=(1024, 768))
		display.start()

		# options = webdriver.ChromeOptions()
		# options.binary_location = '/usr/bin/google-chrome'
		# options.add_argument("--start-maximized");
		# return webdriver.Chrome('/usr/bin/chromedriver', chrome_options=options)
		return webdriver.Firefox(), display

class Robot(object):
	def __init__(self, connector, input_data, output_data):
		self._Init(input_data, output_data)

		try:
			self.driver, self.display = connector()
		except Exception, e:
			Die("Line: {}; Error: {};".format(sys.exc_info()[-1].tb_lineno, e))

	def __del__(self):
		self.ReturnResult()
		self.Close()

	def _Init(self, input_data, output_data):
		self.debug_dir = "./dbg"

		if self.debug_dir:
			if not os.path.exists(self.debug_dir):
				os.mkdir(self.debug_dir)

		self.input_data = input_data
		self.output_data = output_data

		self.result = {}

		self._mandrill = mandrill.Mandrill('U8sEZverxBWrBodUffHSqg')

		try:
			with open(self.input_data, 'r') as content:
				self.input_data = json.loads(content.read())
		except Exception, e:
			self.input_data = {}

	def Close(self):
		self.display.stop()
		self.driver.close()
		self.driver.quit()

	def ExecCmd(self, cmd):
		try:
			getattr(self, cmd)()
		except Exception, e:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback)

			self._dbg('err', full_dump = True)

			Die("Line: {}; Error: {};".format(sys.exc_info()[-1].tb_lineno, e))

	def Get(self, key):
		try:
			value = self.input_data[key]
		except KeyError, e:
			value = None

		return value

	def ClearResults(self):
		self.result = {}

	def AddResult(self, key_value, value = None):
		if value is None:
			for k in key_value:
				self.result[k] = key_value[k]
		else:
			self.result[key_value] = value

	def ReturnResult(self):
		try:
			with open(self.output_data, 'w') as content:
				content.write(json.dumps(self.result))
		except Exception, e:
			pass

	def UploadFile(self, appid, filename, path, filetype, host):
		print('UploadFile: {}'.format([ 'php', '-f', 'upload.php', appid, filename, path, filetype, host if host else '' ]))
		p = subprocess.Popen([ 'php', '-f', 'upload.php', appid, filename, path, filetype, host if host else '' ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		return p.communicate()[0]

	def GetCurrentURL(self):
		return self.driver.current_url

	def GetLog(self, log_type='browser'):
		return self.driver.get_log(log_type)

	def _dbg(self, action, full_dump = False):
		filename = os.path.join(self.debug_dir, "{}-{}.png".format(action, time.time()))
		print('*** DEBUG: {}'.format(filename))
		# for log_type in ('browser', 'driver', 'client', 'server'):
		# 	print('*** LOG({}):'.format(log_type))
		# 	log = self.GetLog(log_type)
		# 	if log:
		# 		for line in log:
		# 			if 'message' in line:
		# 				print line['message']

		self.driver.save_screenshot(filename)

	def _parent(self, node):
		return node.find_element_by_xpath('..')

	def _hover(self, node):
		ActionChains(self.driver).move_to_element(node).perform()

	def _is_checked(self, node):
		return True if self.ExecScript("return arguments[0].checked ? 1 : 0;", node) == 1 else False

	def _click(self, node):
		self.ExecScript("arguments[0].click()", node)

	def _value(self, node):
		try:
			s = self.ExecScript("return arguments[0].value", node)
		except Exception:
			s = '';

		return s;

	def _SetValue(self, node, value):
		try:
			s = self.ExecScript("arguments[0].value = arguments[1]", node, value)
		except Exception:
			return False

		return True

	def _text(self, node):
		try:
			s = self.ExecScript("return arguments[0].innerHTML", node)
		except Exception:
			s = '';

		return s;

	def GetText(self, node):
		try:
			s = self.ExecScript("return arguments[0].innerHTML", node)
		except Exception:
			s = '';

		return s;

	def LoadJQuery(self):
		with open("jquery.js", "r") as content:
			self.ExecScript(content.read())

		jquey_ext = """
		jQuery.fn.justtext = function() { return $(this).clone().children().remove().end().text(); };
		"""

		self.ExecScript(jquey_ext);

	def Visit(self, url):
		self.driver.get(url)

	def ExecScript(self, script, *args):
		return self.driver.execute_script(script, *args)

	def ExecJQueryScript(self, script, *args):
		self.LoadJQuery()
		return self.ExecScript(script, *args)

	def TagElement(self, selector):
		try:
			elem = self.driver.find_element_by_tag_name(selector)
		except Exception:
			elem = None

		return elem

	def TagAllElements(self, selector):
		try:
			elem = self.driver.find_elements_by_tag_name(selector)
		except Exception:
			elem = []

		return elem

	def CSSElement(self, selector):
		try:
			elem = self.driver.find_element_by_css_selector(selector)
		except Exception:
			elem = None

		return elem

	def CSSAllElements(self, selector, parent = None):
		use_parent = self.driver
		if parent: use_parent = parent

		try:
			elem = use_parent.find_elements_by_css_selector(selector)
		except Exception:
			elem = []

		return elem

	def SwitchToFrame(self, frame):
		self.driver.switch_to_frame(frame)

	def XPathElement(self, xpath):
		try:
			elem = self.driver.find_element_by_xpath(xpath)
		except Exception:
			elem = None

		return elem

	def XPathAllElements(self, xpath):
		try:
			elem = self.driver.find_elements_by_xpath(xpath)
		except Exception:
			elem = []

		return elem

	def WaitForElementByXPath(self, xpath, timeout = 10):
		WebDriverWait(self.driver, timeout).until(
			lambda driver : driver.find_element_by_xpath(xpath)
			)

	def WaitForElementByCSS(self, selector, timeout = 10):
		
		WebDriverWait(self.driver, timeout).until(
			lambda driver : driver.find_element_by_css_selector(selector)
			)

	def WaitForElementByTag(self, selector, timeout = 10):
		WebDriverWait(self.driver, timeout).until(
			lambda driver : driver.find_element_by_tag_name(selector)
			)

	def WaitForElementByScript(self, script, timeout = 10):
		WebDriverWait(self.driver, timeout).until(
			lambda driver : driver.execute_script(script)
			)

	def WaitForElementIsVisible(self, node, timeout = 20):
		WebDriverWait(node, timeout).until(
			lambda node : node.is_displayed()
			)

	def SelectByText(self, node, text):
		self.ExecScript(
			"""

			var sel = arguments[0];
			var text = arguments[1];

			for (var i = 0; i < sel.options.length; ++i)
			{
				var v = sel.options[i];

				if (v.text.indexOf(text) >= 0)
				{
					sel.selectedIndex = i;
					break
				}
			}

			var event = document.createEvent("HTMLEvents");
			event.initEvent("change", true, true);
			sel.dispatchEvent(event);

			""", node, text)

	def SelectByValue(self, node, text):
		self.ExecScript(
			"""

			var sel = arguments[0];
			var text = arguments[1];

			for (var i = 0; i < sel.options.length; ++i)
			{
				var v = sel.options[i];

				if (v.value == text)
				{
					sel.selectedIndex = i;
					break
				}
			}

			var event = document.createEvent("HTMLEvents");
			event.initEvent("change", true, true);
			sel.dispatchEvent(event);

			""", node, text)

	def Request(self, url, post = None):
		cookies = ''.join([ "{}={}; ".format(c['name'], c['value']) for c in self.driver.get_cookies() ])

		resp = urllib2.urlopen(urllib2.Request(url, post, { 'Cookie': cookies }))
		data_raw = resp.read()

		for header in resp.info().headers:
			if 'Content-Encoding:' in header and 'gzip' in header:
				return zlib.decompress(data_raw, 16+zlib.MAX_WBITS)

		return data_raw

	def Download(self, url, post = None):
		fd, path = tempfile.mkstemp()
		os.close(fd)

		with open(path, 'wb') as f:
			f.write(self.Request(url, post))

		return path

	def SetWindowSize(self, w, h):
		self.driver.set_window_size(w, h)

	def SendMail(self, to, text):
		try:
			message = { 'to': [ {'email': to} ], 'from_email': 'info@appnow.com', 'from_name': 'Test Report', 'subject': 'Test Report', 'merge_vars': [ {'rcpt': to, 'vars': [ {'content': text, 'name': 'TEXT'} ] } ] }
			self._mandrill.messages.send_template(template_name='any-message-en', message=message, template_content=[{'content': '', 'name': ''}])
		except Exception, e:
			Log(e)
			return False

def IsProcessAlive(pid):
	try:
		os.kill(pid, 0)
	except OSError:
		return False
	else:
		return True

class RobotAWS(Robot):
	def __init__(self, input_data, output_data):
		self._Init(input_data, output_data)

		pid = None

		if os.path.isfile('./xvfb.pid'):
			try:
				with open('./xvfb.pid', 'r') as f:
					pid = int(f.read())
					f.close()
			except Exception, e:
				pid = None

		if pid and not IsProcessAlive(pid):
			self.__RunXvfb()
		elif not pid:
			self.__RunXvfb()

		try:
			options = webdriver.ChromeOptions()
			options.binary_location = '/usr/bin/google-chrome'
			self.driver = webdriver.Chrome('/usr/bin/chromedriver', chrome_options=options)

			# self.driver = webdriver.Chrome(command_executor='http://localhost:4444/wd/hub', desired_capabilities=DesiredCapabilities.CHROME)
		except urllib2.URLError, e:
			pid = None

			if os.path.isfile('./selenium.pid'):
				try:
					with open('./selenium.pid', 'r') as f:
						pid = int(f.read())
						f.close()
				except Exception, e:
					pid = None

			if pid and IsProcessAlive(pid):
				Die("Cannot connect to Selenium 1")
			else:
				pid = os.spawnvpe(os.P_NOWAIT, 'java', [ 'java', '-jar', '/home/admin/selenium/selenium-server-standalone-2.43.1.jar' ], os.environ)

				with open('./selenium.pid', 'w') as f:
					f.write('{}'.format(pid))
					f.close()

				time.sleep(5);

				try:
					self.driver = webdriver.Remote(command_executor='http://localhost:4444/wd/hub', desired_capabilities=DesiredCapabilities.CHROME)
				except Exception, e:
					Die("Cannot connect to Selenium 2")
		except Exception, e:
			Die("Line: {}; Error: {};".format(sys.exc_info()[-1].tb_lineno, e))

	def __RunXvfb(self):
		pid = os.spawnvpe(os.P_NOWAIT, 'Xvfb', [ 'Xvfb', ':10', '-ac', '1024x768x24' ], os.environ)
		with open('./xvfb.pid', 'w') as f:
					f.write('{}'.format(pid))
					f.close()
		time.sleep(5);
		return pid

class FacebookMenu(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

		self._tabs = None

	def _Login(self):
		try:
			self.WaitForElementByCSS('#login_form', 15)
		except Exception, e:
			return

		form = self.CSSElement('#login_form')
		if form:
			self._SetValue(self.CSSElement('#email'), 'enginee777@gmail.com')
			self._SetValue(self.CSSElement('#pass'), 'AppNow777')
			button = self.CSSElement('[name=login]')
			if button:
				self._click(button)
			else:
				button = self.CSSElement('#loginbutton')
				if button:
					self._click(button)

			try:
				self.WaitForElementByXPath("//*[contains(text(), 'Review Recent Login')]", 5)
			except Exception, e:
				pass

			button = self.XPathElement("//button[contains(text(), 'Continue')]")
			if button:
				button.click()

				try:
					self.WaitForElementByXPath("//button[contains(text(), 'Okay')]", 10)
				except Exception, e:
					return

				button = self.XPathElement("//button[contains(text(), 'Okay')]")
				if button:
					button.click()

				try:
					self.WaitForElementByXPath("//button[contains(text(), 'Continue')]", 10)
				except Exception, e:
					return

				button = self.XPathElement("//button[contains(text(), 'Continue')]")
				if button:
					button.click()

				try:
					self.WaitForElementByXPath("//button[contains(text(), 'Continue')]", 10)
				except Exception, e:
					return

				button = self.XPathElement("//button[contains(text(), 'Continue')]")
				if button:
					button.click()

			time.sleep(1)

	def _GetTabs(self, page_id):
		self.Visit("https://www.facebook.com")
		self._Login()

		self.Visit("https://www.facebook.com/{}".format(page_id))

		return self.ExecScript("""
			var tmp = document.querySelectorAll('script');
			for (var i = 0; i < tmp.length; ++i)
			{
				if (tmp[i].innerHTML.indexOf('app_') >= 0 && tmp[i].innerHTML.indexOf('renderPagesNavTabs') >= 0)
				{
					var str = tmp[i].innerHTML;
					var hrefs = str.match(/"href":"(.*?)"/g);
					return JSON.parse('{"urls": [{'+hrefs.join('},{')+'}]}');
				}
			}
			""")

	def CanLoadApp(self, page_id, app_id):
		if self._tabs and 'urls' in self._tabs and self._tabs['urls']:
			app_str = "app_{}".format(app_id)
			for url in self._tabs['urls']:
				if app_str in url['href']:
					return True
			return False
		else:
			return False

		self.Visit("https://www.facebook.com/{}?sk=app_{}".format(page_id, app_id))

		self._Login()

		try:
			self.WaitForElementByTag("iframe", timeout=5)
			iframe = self.TagElement("iframe")
		except Exception, e:
			iframe = None

		return True if iframe else False

	def LoadApp(self, page_id, app_id):
		self.Visit("https://www.facebook.com/{}?sk=app_{}".format(page_id, app_id))

		self._Login()

		#self.WaitForElementByTag("iframe", timeout=15)
		self.WaitForElementByCSS('iframe[name^="app_runner_fb_"]', timeout=600)

		i = 6
		while i > 0:
			try:
				iframe = self.CSSElement('iframe[name^="app_runner_fb_"]')
				iframe.get_attribute("name")
				self.SwitchToFrame(iframe)
				i = 0
			except Exception, e:
				i = i - 1

		#iframe = self.TagElement("iframe")
		#self.SwitchToFrame(iframe)

		#iframes = self.TagAllElements("iframe")
		#for iframe in iframes:
			#if iframe.get_attribute("name") == '':
			#if iframe.get_attribute("name").find("app_runner_fb_") == 0:
				#self.SwitchToFrame(iframe)
				#break

		self.LoadJQuery()

	def Parse(self):
		self._tabs = self._GetTabs(self.Get("page_id"))

		parser = menu.CreateMenuParser(self, self.Get("page_id"))

		if parser:
			print(parser)
			data = parser.Parse()
			self.AddResult(data)
		else:
			data = [];

		return data;

class Flurry(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

	def __Login(self):
		self.Visit('https://dev.flurry.com/secure/login.do')

		self.CSSElement('#emailInput').send_keys('solanove@mail.ru')
		self.CSSElement('#passwordInput').send_keys('AppNow777')
		self.CSSElement('#loginActionForm button').click();

		self.WaitForElementByXPath("//a[contains(text(), 'Home')]")

	def CreateApplication(self):
		platform = self.Get('platform')

		if platform == 'ios':
			url = 'https://dev.flurry.com/iphone_createProject.do'
		elif platform == 'android':
			url = 'https://dev.flurry.com/android_createProject.do'
		else:
			raise Exception('Unknown platform')

		self.__Login()
		self.Visit(url)

		self.CSSElement('#createProjectActionForm_projectName').send_keys(self.Get('name'))
		self.SelectByValue(self.CSSElement('#categoryId'), '1' if platform == 'ios' else '27')

		self.CSSElement('#uploadButton').click()

		error = self.CSSElement('.errorMessage[errorfor]')
		if error:
			raise Exception(self._text(error).strip())

		self.WaitForElementByCSS('.projectKey')
		self.AddResult('id', self._text(self.CSSElement('.projectKey')).strip())

# class GoogleMaps(Robot):
# 	def __init__(self, input_data, output_data):
# 		Robot.__init__(self, input_data, output_data)

# 	def __Login(self):
# 		self.Visit('https://accounts.google.com/ServiceLogin')

# 		self.CSSElement('#Email').send_keys('guskov.eu@gmail.com')
# 		self.CSSElement('#Passwd').send_keys('mgkH4lYn22')
# 		self.CSSElement('#signIn').click();

# 	def CreateApplication(self):
# 		self.__Login()

# 		self.Visit('https://code.google.com/apis/console/?noredirect#project:986201009374:access')
# 		self.WaitForElementByXPath("//h2[contains(text(), 'API Access')]")

# 		self.XPathElement("//span[contains(text(), 'Edit allowed Android apps')]").click()

# 		textarea = self.CSSElement('fieldset textarea')

# 		text = self._value(textarea).strip()
# 		if text:
# 			text = text + "\n"
# 		text = text + "9B:4A:6C:72:E0:19:F6:3E:C6:BF:D7:9B:88:3D:9F:92:1A:A5:D3:0E;{}".format(self.Get('package_name'))

# 		textarea.send_keys(text)

# 		self.XPathElement("//button[contains(text(), 'Update')]").click()

# 		error = self.CSSElement('.errorMessage[errorfor]')
# 		if error:
# 			raise Exception(self._text(error).strip())

# 		self.WaitForElementByCSS('.projectKey')
# 		self.AddResult('id', self._text(self.CSSElement('.projectKey')).strip())

class Apple(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

		self._logged_in = False

	def __Login(self):
		if self._logged_in:
			return

		account = self.Get('account')
		passwd = self.Get('passwd')

		self.AddResult('account', account)
		self.AddResult('passwd', passwd)

		self.Visit('https://developer.apple.com/membercenter/')

		self.WaitForElementByCSS('#accountname')

		self.CSSElement('#accountname').send_keys(account)
		self.CSSElement('#accountpassword').send_keys(passwd)
		self.CSSElement('input[type=submit]').click();

		self.WaitForElementByXPath("//h3[contains(text(), 'Certificates, Identifiers')]")

		self._logged_in = True

	def __Open(self, url, title = None, pre_visit = None, pre_visit_title = None):
		self.__Login()
		if pre_visit:
			self.Visit('https://developer.apple.com/account/ios/{}'.format(pre_visit))

			if pre_visit_title:
				xpath = "//span[contains(text(), '{}')]".format(pre_visit_title)
				self.WaitForElementByXPath(xpath)
				node = self.XPathElement(xpath)

				self.WaitForElementIsVisible(node)

		self.Visit('https://developer.apple.com/account/ios/{}'.format(url))

		if title:
			xpath = "//span[contains(text(), '{}')]".format(title)
			self.WaitForElementByXPath(xpath)
			node = self.XPathElement(xpath)

			self.WaitForElementIsVisible(node)

	def AddProfile(self):
		name = self.Get('name')
		bundle_id = self.Get('bundle_id')

		self.__Open('profile/profileCreate.action', title = 'Provisioning Profile', pre_visit = 'profile/profileList.action?type=production', pre_visit_title = 'Provisioning Profile')

		btn = self.CSSElement('#type-production')
		if not btn:
			btn = self.CSSElement('#type-inhouse')
		btn.click()

		self.CSSElement('.submit').click()

		self.WaitForElementByXPath("//h1[contains(text(), 'Select App ID')]")
		self.SelectByText(self.CSSElement('[name=appIdId]'), bundle_id)
		self.CSSElement('.submit').click()
		
		self.WaitForElementByXPath("//h1[contains(text(), 'Select certificates')]")
		self.CSSAllElements('[name=certificateIds]')[-1].click()
		self.CSSElement('.submit').click()
		
		self.WaitForElementByXPath("//h1[contains(text(), 'Name this profile and generate')]")
		self.CSSElement('[name=provisioningProfileName]').send_keys(name)

		count = 0

		while count < 2:
			count = count + 1

			self.CSSElement('.submit').click()
			time.sleep(1)
			self.CSSElement('.submit').click()
			
			try:
				self.WaitForElementByXPath("//h1[contains(text(), 'Your provisioning profile is ready')]", 60)
			except Exception, e:
				btn = self.CSSElement('a[role=button].ok')
				if btn:
					btn.click()

				continue

			break

	def RegenProfile(self):
		profile_id = self.Get('profile_id')

		self.__Open('profile/profileEdit.action?type=production&provisioningProfileId={}'.format(profile_id), title = 'Provisioning Profile')

		self.CSSElement('.submit').click()
		self.WaitForElementByXPath("//h1[contains(text(), 'Your provisioning profile is ready')]", 60)

	def GetProfileList(self):
		self.__Open('profile/profileList.action?type=production')

		data_url = re.compile('var(?:\s+)profileDataURL(?:\s+)=(?:\s+)"(.*?)";')

		scripts = self.CSSAllElements('script')
		for script in scripts:
			script = self._text(script)

			found = False
			for line in script.split("\n"):
				match = data_url.match(line.strip())
				if match:
					found = True
					url = match.group(1)
					break
			if found: break

		args = url[(url.find('?') + 1) : ]
		url =  url[0 : url.find('?')]

		data = self.Request(url, args+'&pageSize=1000&pageNumber=1&sort=name%3dasc&sidx=name')
		data = json.loads(data)

		profiles = []
		for profile in data['provisioningProfiles']:
			d = {}
			d['profile_id'] = profile['provisioningProfileId']
			d['name'] = profile['name']
			d['status'] = profile['status'].lower()
			d['type'] = profile['type']
			profiles.append(d)

		self.AddResult({ 'profiles': profiles })

		return profiles

	def AddApplication(self):
		self.__Open('identifiers/bundle/bundleCreate.action', title = 'Register iOS App ID')

		app_name = self.Get('app_name')
		bundle = self.Get('bundle')

		self.CSSElement('[name=appIdName]').send_keys(app_name)
		self.CSSElement('[name=explicitIdentifier]').send_keys(bundle)
		self.CSSElement('[name=push]').click()

		self.CSSElement('.submit').click()

		self.WaitForElementByXPath("//h1[contains(text(), 'Confirm your App ID')]")
		self.CSSElement('.submit').click()

	def GetCertificateList(self, inner = False):
		self.__Open('certificate/certificateList.action?type=distribution')

		cert_data_url = re.compile('var(?:\s+)certificateDataURL(?:\s+)=(?:\s+)"(.*?)";')
		cert_types_url = re.compile('var(?:\s+)certificateRequestTypes(?:\s+)=(?:\s+)"(.*?)";')

		found = 0
		scripts = self.CSSAllElements('script')
		for script in scripts:
			script = self._text(script)

			for line in script.split("\n"):
				match = cert_data_url.match(line.strip())				
				if match:
					found = found + 1
					url = match.group(1)
					if found == 2: break

				match = cert_types_url.match(line.strip())
				if match:
					found = found + 1
					types_url = match.group(1)
					if found == 2: break

			if found == 2: break

		url = url + types_url;

		args = url[(url.find('?') + 1) : ]
		url =  url[0 : url.find('?')]

		data = self.Request(url, args)
		data = json.loads(data)

		certs = []
		for cert in data['certRequests']:
			d = {}
			d['cert_id'] = cert['certificateId']
			d['bundle_id'] = cert['name']
			d['can_download'] = cert['canDownload']
			certs.append(d)

		if not inner:
			self.AddResult({ 'certs': certs })

		return certs

	def GetApplicationList(self):
		self.__Open('identifiers/bundle/bundleList.action')

		data_url = re.compile('var(?:\s+)bundleDataURL(?:\s+)=(?:\s+)"(.*?)";')

		scripts = self.CSSAllElements('script')
		for script in scripts:
			script = self._text(script)

			found = False
			for line in script.split("\n"):
				match = data_url.match(line.strip())				
				if match:
					found = True
					url = match.group(1)
					break
			if found: break

		args = url[(url.find('?') + 1) : ]
		url =  url[0 : url.find('?')]

		data = self.Request(url, args)
		data = json.loads(data)

		apps = []
		for app in data['appIds']:
			d = {}
			d['name'] = app['name']
			d['prefix'] = app['prefix']
			d['app_id'] = app['appIdId']
			d['bundle_id'] = app['identifier']
			apps.append(d)

		self.AddResult({ 'apps': apps })

		return apps

	def SavePushCertificate(self):
		cert_id = self.Get('cert_id')

		cert_path = self.DownloadCertificate(cert_id);
		fd, cert_pem_path = tempfile.mkstemp()
		
		os.system("/usr/bin/openssl x509 -in {} -inform DER -out {} -outform PEM".format(cert_path, cert_pem_path));
		os.unlink(cert_path)

		with open(cert_pem_path, 'rb') as f:
			push_cert = f.read()
			f.close()
			os.unlink(cert_pem_path)
			os.close(fd)

		with open('/home/admin/selenium/food/service/push/priv.pem', 'rb') as f:
			push_cert += f.read()
			f.close()

		self.AddResult('cert', push_cert)

	def GeneratePushCertificate(self):
		app_id = self.Get('app_id')
		self.__Open('certificate/certificateRequest.action?appIdId={}&types=3BQKVH9I2X'.format(app_id), title = 'iOS Certificate')

		self.CSSElement('.submit').click()
		
		self.WaitForElementByXPath("//h1[contains(text(), 'Generate your certificate')]")

		self.CSSElement('input[type=file]').send_keys('/home/admin/selenium/food/service/push/req.csr');
		self.CSSElement('.submit').click()

		self.WaitForElementByXPath("//h1[contains(text(), 'Your certificate is ready')]", 60)

	def DownloadCertificate(self, cert_id = None):
		self.__Login()

		save_to = None
		if not cert_id:
			cert_id = self.Get('cert_id')
			save_to = self.Get('save_to')

		path = self.Download('https://developer.apple.com/account/ios/certificate/certificateContentDownload.action?displayId={}&type=3BQKVH9I2X'.format(cert_id))

		if save_to:
			shutil.move(path, save_to)
		else:
			return path

	def DownloadProfile(self, move = True):
		self.__Login()

		profile_id = self.Get('profile_id')
		save_to = self.Get('save_to')
		path = self.Download('https://developer.apple.com/account/ios/profile/profileContentDownload.action?displayId={}'.format(profile_id))
		if move:
			shutil.move(path, save_to)
		else:
			return path

	def SaveProfile(self):
		self.__Login()

		appid = self.Get('appid')
		profile_id = self.Get('profile_id')
		path = self.Download('https://developer.apple.com/account/ios/profile/profileContentDownload.action?displayId={}'.format(profile_id))
		host = self.Get('host')
		suffix = self.Get('suffix')

		if not host:
			host = ''

		print('Saving profile: {}'.format(path))
		print(self.UploadFile(appid, 'app.mobileprovision', path, 'mobileprovision-{}'.format(suffix) if suffix else 'mobileprovision', host))
		
		os.unlink(path)

class Facebook(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

	def _Login(self, login = None, passwd = None):
		try:
			self.WaitForElementByCSS('#login_form', 15)
		except Exception, e:
			return

		form = self.CSSElement('#login_form')
		if form:
			self._SetValue(self.CSSElement('#email'), 'enginee777@gmail.com' if not login else login)
			self._SetValue(self.CSSElement('#pass'), 'AppNow777' if not passwd else passwd)

			button = self.CSSElement('[name=login]')
			if button:
				self._click(button)

			try:
				self.WaitForElementByXPath("//button[contains(text(), 'Okay')]", 5)
				button = self.XPathElement("//button[contains(text(), 'Okay')]")
				button.click()
				
				self.WaitForElementByXPath("//button[contains(text(), 'Okay')]", 5)
				button = self.XPathElement("//button[contains(text(), 'Okay')]")
				button.click()
			except Exception, e:
				pass

			try:
				self.WaitForElementByXPath("//*[contains(text(), 'Review Recent Login')]", 5)
			except Exception, e:
				pass

			button = self.XPathElement("//button[contains(text(), 'Continue')]")
			if button:
				button.click()

				try:
					self.WaitForElementByXPath("//button[contains(text(), 'Okay')]", 10)
				except Exception, e:
					return

				button = self.XPathElement("//button[contains(text(), 'Okay')]")
				if button:
					button.click()
				else:
					return

				try:
					self.WaitForElementByXPath("//button[contains(text(), 'Continue')]", 10)
				except Exception, e:
					return

				button = self.XPathElement("//button[contains(text(), 'Continue')]")
				if button:
					button.click()
				else:
					return

				try:
					self.WaitForElementByXPath("//button[contains(text(), 'Continue')]", 10)
				except Exception, e:
					return

				button = self.XPathElement("//button[contains(text(), 'Continue')]")
				if button:
					button.click()
				else:
					return

		time.sleep(1)

	def RefreshToken(self):
		login = self.Get('login')
		passwd = self.Get('passwd')
		token_index = self.Get('token_index')

		try:
			# url = "https://www.facebook.com/dialog/oauth?client_id=1605912426308309&redirect_uri={}&state={}&scope=publish_stream&response_type=code".format('http%3A%2F%2Ffb.appnow.com:12000%2Ffb%2Ffb-callback.php%3Ftoken_index%3D{}'.format(token_index), hashlib.md5(str(uuid.uuid1())).hexdigest())
			url = "https://www.facebook.com/dialog/oauth?client_id=529675260385339&redirect_uri={}&state={}&scope=publish_stream&response_type=code".format('http%3A%2F%2Ffb.appnow.com:12000%2Ffb%2Ffb-callback.php%3Ftoken_index%3D{}'.format(token_index), hashlib.md5(str(uuid.uuid1())).hexdigest())

			print 'RefreshToken: {} - {} - {} - {}'.format(token_index, login, passwd, url)

			self.Visit(url)
			self._Login(login = login, passwd = passwd)
		except Exception, e:
			print("*** Error: {}".format(e))

	def AddBundleID(self, fb_appid=None, fill_email=False):
		self.SetWindowSize(1024, 768)

		print 'AddBundleID To:', fb_appid

		if fb_appid:
			self.Visit('https://developers.facebook.com/apps/{}/settings/'.format(fb_appid))
		else:
			self.Visit('https://developers.facebook.com/apps/724882300939680/settings/')
			self._Login()

		suffix = self.Get('suffix')
		bundle_id = self.Get('bundle_id')

		if fill_email:
			node = self.CSSElement('input[name="basic_email"]')
			if not self._value(node):
				node = self.XPathElement("//span[contains(text(), 'Contact Email')]/following-sibling::div//input[@type='text']")
				if node:
					node.send_keys("info@appnow.com")

		nodes = self.CSSAllElements('input[name="ios_bundle_id[]"]')
		if nodes:
			ids = bundle_id.split(',')
			fb_ids = [ self._value(node) for node in nodes ]
			bundle_id = ','.join([ v for v in ids if v not in fb_ids ])

		print 'AddBundleID ids:', bundle_id

		node = self.XPathElement("//span[contains(text(), 'Bundle')]/following-sibling::div//input[@type='text']")
		if node and node.is_displayed():
			ids = bundle_id.split(',')
			for i in ids:
				node.send_keys(i)
				node.send_keys(Keys.RETURN)
		else:
			self.XPathElement("//button/span[contains(text(), 'Add Platform')]").click();
			self.WaitForElementByCSS("[data-platform=ios]", 5)

			self._click(self.CSSElement("[data-platform=ios]"))
			time.sleep(1)

			node = self.XPathElement("//span[contains(text(), 'Bundle')]/following-sibling::div//input[@type='text']")

			if node:
				ids = bundle_id.split(',')
				for i in ids:
					node.send_keys(i)
					node.send_keys(Keys.RETURN)

		node = self.CSSElement('input[name="ios_iphone_store_id"]')
		if not self._value(node):
			node.send_keys('284882215')

		node = self.CSSElement('input[name="ios_ipad_store_id"]')
		if not self._value(node):
			node.send_keys('284882215')

		if suffix:
			node = self.XPathElement("//span[contains(text(), 'Suffix')]/following-sibling::div//input[@type='text']")
			if node:
				node.send_keys(suffix)

		node = self.XPathElement("//button[contains(text(), 'Save')]")
		if node:
			self._hover(node)
			node.click()
			node.click()

		try:
			self.WaitForElementByXPath("//button[contains(text(), 'Confirm')]", 5)
			self._click(self.XPathElement("//button[contains(text(), 'Confirm')]"))
			time.sleep(1)
		except Exception, e:
			pass

		try:
			self.WaitForElementByScript("""

				var div = document.evaluate("//div[contains(text(), 'Saved')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
				return (div && div.parentNode && div.parentNode.classList.length > 1) ? div : null;
				
				""", 40)
		except Exception, e:
			pass

	def RemoveApplication(self):
		fb_appid = self.Get('fb_appid')
		
		self.Visit('https://developers.facebook.com/apps/{}/settings/'.format(fb_appid))
		self._Login()

		self.WaitForElementByXPath("//a[contains(text(), 'Delete')]", 15)
		self._click(self.XPathElement("//a[contains(text(), 'Delete')]"))

		#self.WaitForElementByXPath("//button[contains(text(), 'Confirm')]", 5)
		#self._click(self.XPathElement("//button[contains(text(), 'Confirm')]"))

		self.WaitForElementByXPath("//button[contains(text(), 'Delete App')]", 5)
		self._click(self.XPathElement("//button[contains(text(), 'Delete App')]"))

		try:
			self.WaitForElementByCSS("#ajax_password", 5)
			self.CSSElement("#ajax_password").send_keys('AppNow777')
			self.XPathElement("//button[contains(text(), 'Submit')]").click()
		except Exception, e:
			pass

	def AddApplication(self):
		self.Visit('https://developers.facebook.com/quickstarts/?platform=ios')
		self._Login()

		self.WaitForElementByCSS("label>input[aria-autocomplete]", 15)

		name = self.Get('name')
		bundle_id = self.Get('bundle_id')
		fb_appid = self.Get('fb_appid')

		print 'fb_appid:', fb_appid

		if not fb_appid:
			print 'Create NEW fb_appid'

			self.CSSElement("label>input[aria-autocomplete]").send_keys(name)

			try:
				self.WaitForElementByXPath("//span[contains(text(), 'Create New')]", 15)
				self.XPathElement("//span[contains(text(), 'Create New')]").click()

				self.WaitForElementByXPath("//h3[contains(text(), 'Create')]", 15)
				self.WaitForElementByXPath("//button[contains(text(), 'Create')]", 15)
				self._SetValue(self.CSSElement("input[name=app_details_category]"), '1100')

				self._click(self.XPathElement("//button[contains(text(), 'Create')]"))

				self.WaitForElementByXPath("//span[contains(text(), 'Skip Quick')]", 35)
				self._click(self.XPathElement("//span[contains(text(), 'Skip Quick')]"))
				time.sleep(1)
				try:
					self._click(self.XPathElement("//span[contains(text(), 'Skip Quick')]"))
				except Exception, e:
					pass

				# self.WaitForElementByXPath("//div[contains(text(), '{}')]".format(name), 35)

				self.WaitForElementByScript("""
					var divs = document.querySelectorAll('div');
					for (var i in divs)
					{{
						if (divs[i].childNodes && divs[i].childNodes.length > 0 && divs[i].childNodes[0].nodeValue)
						{{
							var s = divs[i].childNodes[0].nodeValue.replace(/[^\w]/g, '');
							if (s.indexOf('{}') >= 0)
							{{
								return divs[i];
							}}
						}}
					}}

					return null;
					
					""".format(name), 35)
			except Exception, e:
				self.WaitForElementByXPath("//div[contains(text(), '{}')]".format(name), 5)
				self.XPathElement("//div[contains(text(), '{}')]".format(name)).click()
				self.XPathElement("//span[contains(text(), 'Skip Quick Start')]").click()
			
			self.XPathElement("//button/span[contains(text(), 'Show')]").click()
			try:
				self.WaitForElementByCSS("#ajax_password", 5)
				self.CSSElement("#ajax_password").send_keys('AppNow777')
				self.XPathElement("//button[contains(text(), 'Submit')]").click()
			except Exception, e:
				pass

			fb_appid = self._text(self.XPathElement("//span[contains(text(), 'App ID')]/following-sibling::div")).strip()
			fb_secret = self._text(self.XPathElement("//span[contains(text(), 'App Secret')]/following-sibling::span//span")).strip()

			self.AddResult('fb_appid', fb_appid)
			self.AddResult('fb_secret', fb_secret)

			print 'fb_appid:',fb_appid
			print 'fb_appid:',fb_secret

		try:
			self.AddBundleID(fb_appid=fb_appid, fill_email=True)
		except Exception, e:
			print e
			self._dbg('add-bundle-error');

		self.Visit('https://developers.facebook.com/apps/{}/review-status/'.format(fb_appid))

		try:
			self._click(self.CSSElement("[type=checkbox]:not([checked])"))

			self.WaitForElementByXPath("//button[contains(text(), 'Confirm')]", 5)
			self._click(self.XPathElement("//button[contains(text(), 'Confirm')]"))
			time.sleep(1)
		except Exception, e:
			pass

class iTunesConnect(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

	def __Login(self):
		self.Visit("https://itunesconnect.apple.com")

		account = self.Get('account')
		passwd = self.Get('passwd')

		self.CSSElement("[name=theAccountName]").send_keys(account)
		self.CSSElement("[name=theAccountPW]").send_keys(passwd)
		self.CSSElement("[name=appleConnectForm]").submit()

		self.LoadJQuery()

	def __PollNodeByCSS(self, selector, tries=20):
		btn = None

		while not btn or not btn.is_displayed():
			tries = tries - 1
			if tries <= 0:
				break;

			time.sleep(1)
			btn = self.CSSElement(selector)

		return btn
		
	def __ManageApps(self):
		self.__Login()

		tries = 20
		btn = None

		while not btn:
			tries = tries - 1
			if tries <= 0:
				break;

			time.sleep(1)
			btn = self.ExecScript(
				"""

				var result;
				$('a>span').each(function (i, v)
				{
					var $v = $(v);
					if ($.trim($v.text()).toLowerCase() == 'my apps')
					{
						result = $v.parent()[0];
						//return false;
					}
				});

				return result;

				""")

		btn.click()

	def __OpenApp(self, app):
		self.__ManageApps()

		self.CSSElement(".seeAll a").click()

		while True:
			app_link = self.ExecJQueryScript(
				"""

				var app_data = $('div.resultList table p a');

				for (var i = 0, j = 0; i < app_data.length; ++i, j += 2)
				{
					var value = app_data[i];

					if ($.trim($(value).text()) == arguments[0])
					{
						return 'https://itunesconnect.apple.com' + $(value).attr('href');
					}
				}

				""", app)

			if app_link:
				self.Visit(app_link)
				break

			next_btn = self.CSSElement(".next a")
			if next_btn:
				next_btn.click()
			else:
				raise Exception('Application not found')

	def __OpenAppCurrentVersion(self, app):
		self.__OpenApp(app)

		self.CSSAllElement('.app-icon a.blue-btn').click()

	def __OpenAppNextVersion(self, app):
		self.__OpenApp(app)

		btns = self.CSSAllElements('.app-icon a.blue-btn')

		if len(btns) != 2:
			return False

		btns[1].click()

		return True

	def __OpenAppRecentVersion(self, app):
		self.__OpenApp(app)

		btns = self.CSSAllElements('.app-icon a.blue-btn')
		btns[len(btns) - 1].click()

	def __Fill(self, name, value, tag = 'input', clear = True, select_by_value = False):
		tries = 20
		while True:
			tries = tries - 1
			if tries <= 0:
				break

			element = self.XPathAllElements("//label[contains(text(), {})]/following-sibling::span/{}".format(XPathEscape(name), tag))
			element = element[-1]
			if element and element.is_displayed():
				break
			else:
				time.sleep(1)

		self._hover(element)

		if clear:
			element.clear()

		if tag == 'select':
			if select_by_value:
				self.SelectByValue(element, value)
			else:
				self.SelectByText(element, value)
		else:
			element.send_keys(value)
			# self._SetValue(element, value)

	def __Upload(self, upload_id, screens, change_icon = False):
		tmp_files = urllib2.urlopen(urllib2.Request("http://srv.appnow.com:8383/tmp.php", data = urllib.urlencode( { 'cmd': 'create', 'files[]': screens }, True ))).read()
		tmp_files = json.loads(tmp_files)

		idx = 1

		tmp_files_remove = []
		for screen in tmp_files['data']:
			tmp_files_remove.append(screen['path'])

			if change_icon:
				self.ExecScript(
					"""

						var node = document.getElementById('lcUploaderImageContainer_largeAppIcon');
						while (node.firstChild)
						{
							node.removeChild(node.firstChild);
						}

					""")

			self.CSSElement('#fileInput_{}'.format(upload_id)).send_keys(screen['path'])

			if change_icon:
				self.ExecScript(
				"""

				if (typeof(window.__uploaders) === 'undefined')
				{
					window.__uploaders[0].submitUpload();
				}

				""")

			self.WaitForElementByCSS("#lcUploaderImageContainer_{} .lcUploaderImage[id]:nth-child({})".format(upload_id, idx), timeout=30)

			idx = idx + 1

		return tmp_files_remove

	def __GetErrors(self):
		res = []

		errors = self.CSSAllElements('#headerMessagesUpdateContainer li')
		for err in errors:
			res.append(err.text)

		return res

	def AddVersion(self):
		if not self.__OpenAppNextVersion(self.Get('app')):
			return False;

		self.__Fill('Version Number', self.Get('version'))
		self.__Fill('What\'s New in this Version', u'Исправление ошибок', tag = 'textarea')

		self.CSSElement(".wrapper-right-button input").click()

		return True

	def AddApplication(self):
		self.__ManageApps()

		btn = self.__PollNodeByCSS('.new-button')
		btn.click()

		btn = self.__PollNodeByCSS("[ng-if=canCreateIOSApps]")
		self._click(btn)

		self.WaitForElementByXPath("//h1[contains(text(), 'New iOS App')]", 60)

		self.__Fill('Name', self.Get('name'))
		self.__Fill('SKU', hashlib.sha1(str(self.Get('appid'))).hexdigest())
		self.__Fill('Bundle ID', self.Get('bundle_id'), tag = 'select', clear = False)
		self.__Fill('Primary Language', 'Russian', tag = 'select', clear = False)
		self.__Fill('Version', '1.0.0')

		self.CSSElement(".right-buttons button.primary").click()

		# errors = self.__GetErrors()
		# if len(errors) > 0:
		# 	self.AddResult("errors", errors)
		# 	return

		# self.SelectByText(self.CSSElement('#pricingPopup'), 'Free')
		# self.CSSElement(".wrapper-right-button input").click()

		# self.__Fill('Copyright', 'Appnow LLC')

		# self.__Fill('Support URL', 'http://appnow.com')
		# self.__Fill('First Name', 'Alexey')
		# self.__Fill('Last Name', 'Shishkov')
		# self.__Fill('Email Address', 'info@appnow.com')
		# self.__Fill('Phone Number', '+79250029888')

		# self.__Fill('Username', '+79250776273')
		# self.__Fill('Password', 'yofdmgqc')

		# self.__Fill('Primary Category', self.Get('category'), tag = 'select', clear = False, select_by_value = True)
		# self.__Fill('Secondary Category', self.Get('category2'), tag = 'select', clear = False, select_by_value = True)
		# self.__Fill('Description', self.Get('description'), tag = 'textarea')
		# self.__Fill('Keywords', self.Get('keywords'))

		# btns = self.CSSAllElements('.br-1')
		# for btn in btns:
		# 	btn.click()

		# self.ExecScript("window.scrollTo(0,document.body.scrollHeight);");

		# tmp_files_remove = []
		# tmp_files_remove = tmp_files_remove + self.__Upload('largeAppIcon', [ self.Get('icon') ])
		# tmp_files_remove = tmp_files_remove + self.__Upload('35InchRetinaDisplayScreenshots', self.Get('screens_3_5'))
		# tmp_files_remove = tmp_files_remove + self.__Upload('iPhone5', self.Get('screens_4'))
		# tmp_files_remove = tmp_files_remove + self.__Upload('iPadScreenshots', self.Get('screens_ipad'))

		# self.CSSElement(".wrapper-right-button a").click()

		# self.ExecScript("window.scrollTo(0,0);");

		# urllib2.urlopen(urllib2.Request("http://srv.appnow.com:8383/tmp.php", data = urllib.urlencode( { 'cmd': 'remove', 'files[]': tmp_files_remove }, True )))

		# errors = self.__GetErrors()
		# if len(errors) > 0:
		# 	self.AddResult("errors", errors)
		# 	return

	def GetApplicationList(self):
		self.__ManageApps()

		time.sleep(10)

		prev_hash = None
		apps = []

		while True:
			chunk = self.ExecJQueryScript(
				"""

				var rows = $('li.app');

				var apps = [];
				for (var i = 0; i < rows.length; ++i)
				{
					var $row = $(rows[i]);

					apps.push(
						{
							 name: $.trim($row.find('[bo-bind="app.name"]').text())
							// ,status: $.trim(state_data[j].innerHTML)
							// ,version: $.trim(version_data[j].innerHTML)
							,store_id: $row.find('[bo-bind="app.name"]').parent().attr('href').match(/\/(\d+)$/)[1]
						});
				}

				return apps;

				""")

			current_hash = hashlib.md5(json.dumps(chunk)).hexdigest()
			if current_hash == prev_hash or not current_hash:
				break

			prev_hash = current_hash

			apps = apps + chunk

			next_btn = self.CSSAllElements("#pagination a")
			if next_btn:

				if self.ExecScript("return document.getElementById('pages').innerHTML.match(/Page (\d+) of \1/) !== null ? 1 : 0;") == 1:
					break
				
				next_btn = next_btn[-1]
				if next_btn.is_displayed() and next_btn.is_enabled():
					next_btn.click()
				else:
					break
			else:
				break

		self.AddResult({ 'apps': apps })

	def EditApp(self):
		app = self.Get('app')

		self.__OpenAppRecentVersion(app)

		self.ExecScript(
			"""

			var original = LCUploaderImages.prototype.initialize;

			LCUploaderImages.prototype.initialize = function ()
			{
				original.apply(this, arguments);

				if (typeof(window.__uploaders) === 'undefined')
				{
					window.__uploaders = [];
				}

				window.__uploaders.push(this);
			}

			""");

		btns = self.CSSAllElements('.small-grey-btn')
		btns[0].click()
		self.WaitForElementByXPath("//span[contains(text(), 'Edit Version Information')]")

		try:
			btns = self.CSSAllElements('.br-1')
			for btn in btns:
				btn.click()
		except Exception, e:
			pass

		self.ExecScript(
			"""
				var node = document.getElementById('versionInfoLightbox-overlayScroll');
				node.scrollTop = node.scrollHeight;

			""");

		tmp_files_remove = []
		tmp_files_remove = tmp_files_remove + self.__Upload('largeAppIcon', [ self.Get('params')['icon'] ], change_icon = True)

		self.CSSElement('#lightboxSaveButtonEnabled').click()

		while self.CSSElement('#versionInfoLightbox-overlayScroll').is_displayed():
			time.sleep(1)

		btns = self.CSSAllElements('.small-grey-btn')
		btns[1].click()
		self.WaitForElementByXPath("//span[contains(text(), 'Edit Russian')]")

		btns = self.CSSAllElements('.lcUploaderImageDelete')

		for btn in btns:
			btn.click()
			time.sleep(1)

		tmp_files_remove = tmp_files_remove + self.__Upload('35InchRetinaDisplayScreenshots', self.Get('params')['screens_3_5'])
		tmp_files_remove = tmp_files_remove + self.__Upload('iPhone5', self.Get('params')['screens_4'])
		tmp_files_remove = tmp_files_remove + self.__Upload('iPadScreenshots', self.Get('params')['screens_ipad'])

		urllib2.urlopen(urllib2.Request("http://srv.appnow.com:8383/tmp.php", data = urllib.urlencode( { 'cmd': 'remove', 'files[]': tmp_files_remove }, True )))

		self.__Fill('Description', self.Get('params')['description'], tag = 'textarea')
		self.__Fill('Keywords', self.Get('params')['keywords'])

		self.CSSElement('#lightboxSaveButtonEnabled').click()

	def MakeReadyForUpload(self):
		app = self.Get('app')

		self.__OpenAppRecentVersion(app)

		try:
			self.CSSElement('.wrapper-topright-button a').click()
			btn = self.CSSElement('[name=encryptionHasChanged][value=false]')
			if btn and btn.is_displayed():
				btn.click()
			btn = self.CSSElement('[name=firstQuestionRadio][value=false]')
			if btn and btn.is_displayed():
				btn.click()
			btn = self.CSSElement('[name=ipContentsQuestionRadio][value=true]')
			if btn and btn.is_displayed():
				btn.click()
			btn = self.CSSElement('[name=ipRightsQuestionRadio][value=true]')
			if btn and btn.is_displayed():
				btn.click()
			btn = self.CSSElement('[name=booleanRadioButton][value=false]')
			if btn and btn.is_displayed():
				btn.click()

			self.CSSElement('.wrapper-right-button input').click()
		except Exception, e:
			return False

	def IsAppNameValid(self):
		self.__ManageApps()

		self.CSSElement(".upload-app-button a").click()

		self.__Fill('App Name', self.Get('name'))

		self.CSSElement(".wrapper-right-button input").click()

		errors = self.__GetErrors()

		if len(errors) <= 0:
			self.AddResult('valid', 1)
		else:
			found = False
			for err in errors:
				if err.lower().find('app name you entered has already been used') >= 0:
					found = True
					break

			if found:
				self.AddResult('valid', 0)
			else:
				self.AddResult('valid', 1)

class GooglePlay(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

		self._service = None

	def __InitGooglePlayService(self):
		if self._service:
			return

		with open("google/googleapiclient/appnow.p12") as f:
			private_key = f.read()

		credentials = SignedJwtAssertionCredentials('986742683029-875mk4alqtdm6267m35qncqnesqiq17e@developer.gserviceaccount.com', private_key, 'https://www.googleapis.com/auth/androidpublisher')

		self._service = discovery.build('androidpublisher', 'v2', http = credentials.authorize(http = httplib2.Http()))

	def __Login(self):
		self.Visit("https://play.google.com/apps/publish/v2/")

		form = self.CSSElement("#gaia_loginform")
		if form:
			try:
				account = self.Get('account')
			except Exception, e:
				raise Exception('Wrong Google Play Account')

			try:
				passwd = self.Get('passwd')
			except Exception, e:
				passwd = 'AppNow777'

			if not passwd:
				passwd = 'AppNow777'

			if not account:
				raise Exception('Wrong Google Play Account')

			self.CSSElement("#Email").send_keys(account)
			self.CSSElement("#Passwd").send_keys(passwd)

			self.CSSElement("#gaia_loginform").submit()

		try:
			self.WaitForElementByXPath("//span[contains(text(), 'Add new application')]")
		except Exception, e:
			btn = self.CSSElement('a[href="#AppListPlace"]')
			self._click(btn)
			self.WaitForElementByXPath("//span[contains(text(), 'Add new application')]")

	def __NextPage(self):
		go_button = self.XPathElement(str((u"//div[normalize-space(text()) = '"+unichr(9654)+"']").encode('utf-8')))
		if go_button:
			go_button_parent = self._parent(go_button)
			if go_button_parent and go_button_parent.is_enabled() and go_button.is_displayed():
				go_button.click()
				return True
			return False

	def __CreateApp(self, name, apk):
		self.XPathElement("//*[normalize-space(text()) = 'Add new application']").click()

		self.WaitForElementByCSS("div.popupContent input", 10)

		name_input = next((x for x in self.CSSAllElements("div.popupContent input") if x.is_displayed()), None)
		name_input.send_keys(name)

		self.XPathElement("//*[normalize-space(text()) = 'Upload APK']").click()
		self.WaitForElementByXPath("//span[contains(text(), 'Draft')]")

		apk_path = self.Download(apk)

		try:
			os.rename(apk_path, '{}.apk'.format(apk_path))
			apk_path = '{}.apk'.format(apk_path)
			self.__UploadApk(apk_path)
		finally:
			os.unlink(apk_path)

	def __OpenApp(self, name):
		app = self.XPathElement("//a[@data-column='TITLE']/span[contains(text(), {})]".format(XPathEscape(name)))
		if not app:
			if self.__NextPage():
				return self.__OpenApp(name)
			else:
				return False
		else:
			app.click()

			self.WaitForElementByXPath("//span[contains(text(), {})]".format(XPathEscape(name)))
			self.WaitForElementByXPath("//h3[contains(text(), 'Store Listing')]")

		return True

	def __Fill(self, element, value):
		element.clear()
		element.send_keys(value)

	def __Upload(self, screens, offset = 0):
		tmp_files = urllib2.urlopen(urllib2.Request("http://srv.appnow.com:8383/tmp.php", data = urllib.urlencode( { 'cmd': 'create', 'files[]': screens }, True ))).read()
		tmp_files = json.loads(tmp_files)

		files = self.CSSAllElements("input[type=file]")
		divs_count = len(self.CSSAllElements('img[height="150"][src^=http]'))

		idx = offset
		tmp_files_remove = []
		for screen in tmp_files['data']:
			tmp_files_remove.append(screen['path'])

			files[idx].send_keys(screen['path'])

			fail = True
			timeout = 30
			while timeout >= 0:
				if divs_count == len(self.CSSAllElements('img[height="150"][src^=http]')):
					timeout = timeout - 1
					time.sleep(1)
					continue

				fail = False
				divs_count = len(self.CSSAllElements('img[height="150"][src^=http]'))
				break

			if fail:
				raise Exception('Cannot upload screenshots')
			
			idx = idx + 1
			files = self.CSSAllElements("input[type=file]")

		return tmp_files_remove, idx + 1

	def __Save(self):
		save = self.XPathAllElements("//*[normalize-space(text()) = 'Save']")
		if not save:
			save = self.XPathAllElements("//*[normalize-space(text()) = 'Save and publish']")

		if len(save) >= 2:
			save = save[1]
		elif save:
			save = save[0]

		if save:
			save.click()

			try:
				self.WaitForElementByXPath("//*[normalize-space(text()) = 'Saved']")
			except Exception, e:
				pass

	def __FillStoreListing(self):
		inputs = self.CSSAllElements("fieldset input")
		textareas = self.CSSAllElements("fieldset textarea")
		selects = self.CSSAllElements("fieldset select")

		self.__Fill(inputs[0], self.Get('name'))
		self.__Fill(inputs[2], 'http://appnow.com')
		self.__Fill(inputs[3], 'info@appnow.com')
		self.__Fill(inputs[4], '+79250029888')
		self.__Fill(inputs[5], 'http://appnow.com')

		self.__Fill(textareas[0], self.Get('description'))

		self.SelectByValue(selects[0], 'APPLICATION')
		self.SelectByValue(selects[1], self.Get('category'))

		try:
			self.SelectByValue(selects[3], 'SUITABLE_FOR_ALL')
		except Exception, e:
			self.SelectByValue(selects[2], 'SUITABLE_FOR_ALL')

		self.ExecJQueryScript(
			"""

			var $btns = $('img+div+div')
			for (var i = 0; i < $btns.length; ++i)
			{
				$btns[i].click();
			}

			""")

		imgs = self.CSSAllElements('img[height="150"][src^=http]')
		for img in imgs:
			self.ExecScript("arguments[0].setAttribute('src', '')", img)

		self.ExecScript("window.GetOffsetTop = function (node) { var res = node.offsetTop; while (node.offsetParent) { res += node.offsetParent.offsetTop; node = node.offsetParent; } return res; }")

		tmp_files_remove = []

		self.ExecScript("window.scrollTo(0, GetOffsetTop(arguments[0]) - 125);", self.XPathElement("//b[contains(text(), 'Phone')]"))
		tmp, offset = self.__Upload(self.Get('screens_phone'))
		tmp_files_remove = tmp_files_remove + tmp

		self.ExecScript("window.scrollTo(0, GetOffsetTop(arguments[0]) - 125);", self.XPathElement("//b[contains(text(), '7-inch')]"))
		tmp, offset = self.__Upload(self.Get('screens_7'), offset)
		tmp_files_remove = tmp_files_remove + tmp

		self.ExecScript("window.scrollTo(0, GetOffsetTop(arguments[0]) - 125);", self.XPathElement("//b[contains(text(), '10-inch')]"))
		tmp, offset = self.__Upload(self.Get('screens_10'), offset)
		tmp_files_remove = tmp_files_remove + tmp

		self.ExecScript("window.scrollTo(0, GetOffsetTop(arguments[0]) - 125);", self.XPathElement("//h5[contains(text(), 'Hi-res icon')]"))
		tmp, offset = self.__Upload([ self.Get('icon') ], offset)
		tmp_files_remove = tmp_files_remove + tmp

		urllib2.urlopen(urllib2.Request("http://srv.appnow.com:8383/tmp.php", data = urllib.urlencode( { 'cmd': 'remove', 'files[]': tmp_files_remove }, True )))

		self.__Save()

	def __UploadApk(self, apk_path):
		self.ExecScript("window.scrollTo(0, 0);")

		self._click(self.CSSElement("a[href*=Apk]"))

		self.WaitForElementByXPath("//h3[contains(text(), 'APK')]")

		btn = self.XPathAllElements("//*[normalize-space(text()) = 'Upload your first APK to Production']")
		if len(btn) < 2:
			btn = self.XPathElement("//*[normalize-space(text()) = 'Upload new APK to Production']")
		else:
			btn = btn[1]

		btn.click()

		self.WaitForElementByXPath("//h3[contains(text(), 'Upload new APK to Production')]")
		self.WaitForElementByXPath("//div[contains(text(), 'Browse files')]")

		self.ExecScript("""

			arguments[0].style.visibility = 'visible';
			arguments[0].style.height = '40px';

			""", self.CSSElement("input[type=file]"))

		self.CSSElement("input[type=file]").send_keys(apk_path)

		while True:
			progress = self.CSSElement('.popupContent div[style*="width:"]')

			if not progress:
				break

			progress = progress.get_attribute('style')
			progress = int(progress[len('width:'):progress.find('%')])

			error_msg = self.CSSElement('.popupContent h4+div p')
			if error_msg:
				print('Upload APK Error: <b>{}</b>'.format(self._text(error_msg)))

			if progress >= 100:
				break;

			time.sleep(1)

	def __FillPricing(self):
		self.ExecScript("window.scrollTo(0, 0);")

		self._click(self.CSSElement("a[href*=Pricing]"));
		self.WaitForElementByXPath("//h3[contains(text(), 'Pricing & Distribution')]")

		checkboxes = self.CSSAllElements("input[type=checkbox]")
		btn = checkboxes[1]
		if not self._is_checked(btn):
			btn.click()

		btn = checkboxes[len(checkboxes) - 1]
		if not self._is_checked(btn):
			btn.click()

		btn = checkboxes[len(checkboxes) - 2]
		if not self._is_checked(btn):
			btn.click()

		self.__Save()

	def __Finalize(self):
		self.ExecScript("window.scrollTo(0, 0);")

		self.WaitForElementByXPath("//span[contains(text(), 'Publish this app')]")
		self._click(self.XPathElement("//span[contains(text(), 'Publish this app')]"))
		self._click(self.XPathElement("//span[contains(text(), 'Re-publish this app')]"))

		self.WaitForElementByXPath("//span[contains(text(), 'Published')]")

	def GetApplicationList(self):
		self.__Login();

		try_left = 20
		data = []
		while True:
			time.sleep(1)

			apps = self.CSSAllElements('tbody a>span')

			data_chunk = []
			try_again = False
			for i in range(0, len(apps), 2):
				t = self._text(apps[i + 1])
				if not t or t.lower() == '':
					try_again = True;
					break;
				data_chunk.append({ 'name': self._text(apps[i]), 'status': self._text(apps[i + 1]).lower() })

			if try_again:
				try_left = try_left - 1
				if try_left < 0:
					return
				else:
					continue
			else:
				data = data + data_chunk
			
			if self.__NextPage():
				try_left = 20
				continue
			else:
				break

		self.AddResult("apps", data)

	def Publish(self):
		self.__Login();

		if not self.__OpenApp(self.Get('name')):
			self.__CreateApp(self.Get('name'))

		self.__FillStoreListing()
		self.__UploadApk()
		self.__FillPricing()
		self.__Finalize()

	def IsApplicationExists(self, package_name = None):
		self.__InitGooglePlayService()

		if not package_name:
			package_name = self.Get('package_name')

		try:
			edit_request = self._service.edits().insert(body={}, packageName=package_name)
			if 'id' in edit_request.execute():
				self.AddResult('apps', [ package_name ])
				return True
		except Exception, e:
			pass

		self.AddResult('apps', [])
		return False

	def AddApplication(self):
		self.__InitGooglePlayService()
		self.__Login()

		package_name = self.Get('package_name')

		if self.IsApplicationExists(package_name):
			return

		try:
			self.__CreateApp(self.Get('name'), self.Get('apk'))
		finally:
			self.IsApplicationExists(package_name)

	def UploadAPK(self):
		self.__InitGooglePlayService()

		apk = self.Get('apk')
		package_name = self.Get('package_name')

		apk_path = self.Download(apk)

		try:
			os.rename(apk_path, '{}.apk'.format(apk_path))
			apk_path = '{}.apk'.format(apk_path)

			edit_request = self._service.edits().insert(body={}, packageName=package_name)
			result = edit_request.execute()
			edit_id = result['id']

			apk_response = self._service.edits().apks().upload(editId=edit_id, packageName=package_name, media_body=apk_path).execute()
			print apk_response

		finally:
			os.unlink(apk_path)

class Appnow(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

	def __ReportError(self, message):
		self.SendMail('guskov.eu@gmail.com', message)
		self.SendMail('solanove@mail.ru', message)
		self.SendMail('duke-nod@yandex.ru', message)

	def TestLanding(self):
		try:
			self.Visit('http://cp.appnow.com')

			self.ExecScript("""
				$('a[href=#getStartedModal]')[0].click();
				""")
			time.sleep(5)

			self.CSSElement('#popup_app_create_social_id').send_keys('xxx')
			time.sleep(5)

			self.WaitForElementByCSS('.ui-autocomplete', 30)
		except Exception, e:
			self.__ReportError('Search on /core/index is broken! Fix it!')

class Instagram(Robot):
	def __init__(self, *args):
		Robot.__init__(self, *args)

	def Login(self):
		login = self.Get('login')
		password = self.Get('password')

		self.Visit('https://apigee.com/console/instagram')

		self.WaitForElementByCSS('#oauth2', 60)

		self.CSSElement('#oauth_dropdown').click();
		time.sleep(1)
		self.CSSElement('#oauth2').click();
		time.sleep(1)

		self.WaitForElementByXPath("//a[contains(text(), 'Sign in with Instagram')]", 60)
		self.XPathElement("//a[contains(text(), 'Sign in with Instagram')]").click()

		self.WaitForElementByCSS("#login-form", 60)
		self.CSSElement('#login-form [name=username]').send_keys(login)
		self.CSSElement('#login-form [name=password]').send_keys(password)
		self.CSSElement('#login-form [type=submit]').click()
		time.sleep(1)

		btn = self.CSSElement('[type=submit][value=Authorize]')
		if btn:
			btn.click()

		self.WaitForElementByCSS("[id='oauth2#instagram-AuthenticatedUser']", 60)
		self.CSSElement('#oauth_dropdown').click();
		time.sleep(1)
		self.CSSElement("[id='oauth2#instagram-AuthenticatedUser']").click();
		time.sleep(1)

		self.Visit('https://apigee.com/console/instagram?req=%7B%22resource%22%3A%22get_users_feed%22%2C%22params%22%3A%7B%22query%22%3A%7B%7D%2C%22template%22%3A%7B%7D%2C%22headers%22%3A%7B%7D%2C%22body%22%3A%7B%22attachmentFormat%22%3A%22mime%22%2C%22attachmentContentDisposition%22%3A%22form-data%22%7D%7D%2C%22verb%22%3A%22get%22%7D');
		time.sleep(5)
		self.WaitForElementByCSS("#send_button", 60)
		self.CSSElement('#send_button').click()
		time.sleep(5)

		resp = self._text(self.CSSElement('#request_container strong'))
		self.AddResult('token', re.search('\?access_token=([\w\.]+)', resp).group(1))

		print 'Token:',re.search('\?access_token=([\w\.]+)', resp).group(1)

def main():
	if len(sys.argv) < 5:
		Die("Usage: {} <robot-name> <cmd> <input> <output> <connection>".format(sys.argv[0]));

	connector = None
	if len(sys.argv) >= 6 and sys.argv[5] == 'aws':
		connector = DriverConnectorAWS();
	else:
		connector = DriverConnector();

	name = sys.argv[1]
	cmd = sys.argv[2]

	input_data = sys.argv[3]
	output_data = sys.argv[4]

	robot = None
	if name == 'facebook_menu':
		robot = FacebookMenu(connector, input_data, output_data)
	elif name == 'facebook':
		robot = Facebook(connector, input_data, output_data)
	elif name == 'flurry':
		robot = Flurry(connector, input_data, output_data)
	elif name == 'apple':
		robot = Apple(connector, input_data, output_data)
	elif name == 'itunes_connect':
		robot = iTunesConnect(connector, input_data, output_data)
	elif name == 'google_play':
		robot = GooglePlay(connector, input_data, output_data)
	elif name == 'appnow':
		robot = Appnow(connector, input_data, output_data)
	elif name == 'instagram':
		robot = Instagram(connector, input_data, output_data)

	if robot:
		robot.ExecCmd(cmd)
	else:
		Die('Unknown Robot: {}'.format(name))

if __name__ == '__main__':
	main()
