#!/usr/bin/env python3
'''price_tracker.py script parse products pages and compares their prices with
your price. all data is stored in google spreadsheets'''


import os
import requests
import re
import bs4
from proxy_requests import ProxyRequests
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
import json
import time
from time import localtime, strftime
from colorama import Fore, Style


class PriceTracker(object):
    def __init__(self):
        self.regex_url = re.compile(r'^(?:http|ftp)s?://')
        self.regex_email = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
        self.regex_domain = re.compile(
            r'(www)?(.*)([\.]+)(.*)?([\.]+)?(com|net|org|info|coop|int|co\.uk'
            r'|org\.uk|ac\.uk|uk)'
        )

    # function to get price from the desire url
    def bs_scrap_price(self, shop_link, domain, price_tag_name, 
                    price_attr_name, price_tag_name_2, price_attr_values,
                    title_tag_name, title_attr_name, title_attr_value):
        n = 3
        while n > 0:
            user_agents = ['Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:70.0)'
                           ' Gecko/20100101 Firefox/70.0',
                           'Mozilla/5.0 (X11; Linux x86_64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko)'
                           'Ubuntu Chromium/77.0.3865.90 Chrome/77.0.3865.90'
                           ' Safari/537.36',
                           'Opera/9.80 (X11; Linux i686; Ubuntu/14.10) '
                           'Presto/2.12.388 Version/12.16']

            # random choose user agent to hide your bot for the site
            user_agent = random.choice(user_agents)
            header = {'User-Agent': user_agent,
                      'Host': domain,
                      'Accept': 'text/html,application/'
                      'xhtml+xml,'
                      'application/xml;q=0.9,*/*;q=0.8',
                      'Accept-Language': 'en-us,en;q=0.5',
                      'Accept-Encoding': 'gzip,deflate',
                      'Accept-Charset': 'ISO-8859-1,'
                      'utf-8;q=0.7,*;q=0.7',
                      'Keep-Alive': '115',
                      'Connection': 'keep-alive'}
            try:
                r = ProxyRequests(shop_link)
                r.set_headers(header)
                r.get_with_headers()    
                res = str(r)
            except Exception as error:
                return False, error
            if str(res) == '<Response [404]>':  # handling 404 error exception
                error = 'The page was not found'
                return False, error

            # creating soup object of the source
            soup = bs4.BeautifulSoup(res, features="html.parser")
            price = product_title = None
            for price_attr_value in price_attr_values: 
                # finding price on the page
                try:
                    if price_tag_name_2 == "":
                        price = str(soup.find(price_tag_name, attrs={
                            price_attr_name: price_attr_value}))
                    else:
                        price = str(soup.find(price_tag_name, attrs={
                            price_attr_name: price_attr_value}).find(price_tag_name_2))
                        print(price)
                    product_title = (soup.find(title_tag_name,
                                        {title_attr_name: title_attr_value})
                                        .text.lstrip())
                except Exception:
                    pass
            # if price isn't None breake the while loop and continues
            # our function
            if price != None and product_title != None:
                return price, product_title.lstrip()
            n -= 1
            time.sleep(random.randint(5, 10))

        return False, "Can't find price or product title on the web page"

    def selenium_scrap_price(self, shop_link, domain,
                            price_attr_values, title_attr_value):
        price = None

        try:
            # fireFoxOptions = webdriver.FirefoxOptions()
            fireFoxOptions = Options()
            fireFoxOptions.binary_location = os.environ.get("FIREFOX_BIN")
            # fireFoxOptions.add_argument("--headless")
            # fireFoxOptions.add_argument("--disable-dev-shm-usage")
            # fireFoxOptions.add_argument("--no-sandbox")
            fireFoxOptions.headless = True
            print('fireFoxOptions.headless = True - DONE')
            browser = webdriver.Firefox(executable_path=os.environ.get("GECKODRIVER_PATH"), options=fireFoxOptions)
            print(browser)
            browser.get(shop_link)
            print('browser.get(shop_link) - DONE')

            product_title = browser.find_element_by_class_name(title_attr_value).text

            for price_attr_value in price_attr_values:
                try:
                    price = browser.find_element_by_class_name(price_attr_value).text
                    if price != None:
                        return price, product_title
                except:
                    pass
        except Exception as error:
            print(str(error))
        finally:
            try:
                browser.close()
            except Exception:
                print('exception at browser.close()')

        return False, "Can't find price on the web page"

    def price_check(self, price, product_title, your_price, email, shop_link):
        try:
            price_regex = re.compile(r'[0-9]+\.?[0-9]*')
            price = float(price_regex.search(price).group())
            print(f'The price of {Style.BRIGHT}"{product_title}"'
                  f'{Style.RESET_ALL} is {Style.BRIGHT}"{price}"'
                  f'{Style.RESET_ALL} and your prise '
                  f'is {Style.BRIGHT}"{your_price}"{Style.RESET_ALL}')
            if your_price > price:
                self.send_email(email, shop_link, product_title, your_price, price)
                result_message = (f'{strftime("%Y-%m-%d %H:%M:%S", localtime())}\n'
                                '*********************************\n'
                                f'The price ({price}) of {product_title}'
                                f' is low enough. The email was sent.\n'
                                '*********************************\n')
                return "cheap", result_message
            else:
                result_message = (f'{strftime("%Y-%m-%d %H:%M:%S", localtime())}\n'
                                  f'The price of "{product_title}" '
                                  f'({price}) is still higher than your. You '
                                  f'should to wait.\n')
                return "expensive", result_message
        except Exception as error:
            return False, f'{strftime("%Y-%m-%d %H:%M:%S", localtime())}\n{str(error)}'

    def parse_shop_list(self):
        for row in range(2, self.max_row_ws + 1):
            gspread_row_values = self.ws.row_values(row)
            parse_dict = self.gspread_data_checker(gspread_row_values)
            error = '\n'.join(parse_dict['error'])
            row_url = parse_dict['row_url']
            domain = parse_dict['domain'][8:]
            row_price = parse_dict['row_price']
            row_email = parse_dict['row_email']  
            row_repeat = parse_dict['row_repeat'] 

            print(f'Checking price of product at {Style.BRIGHT}"{row_url}"\
                    {Style.RESET_ALL}')
            # start loop for repetative tor request till price not equale None,
            # count_try - number of tries

            for x in self.my_dict:
                # if x (domain from the json file) is in shop_link string
                if x in row_url:
                    # copy tags and args for certain domain
                    parser = self.my_dict[x]['parcer']
                    price_tag_name = self.my_dict[x]['price_tag_name']
                    price_tag_name_2 = self.my_dict[x]['price_tag_name_2']
                    price_attr_name = self.my_dict[x]['price_attr_name']
                    price_attr_values = self.my_dict[x]['price_attr_values']
                    title_tag_name = self.my_dict[x]['title_tag_name']
                    title_attr_name = self.my_dict[x]['title_attr_name']
                    title_attr_value = self.my_dict[x]['title_attr_value']

            if error == '' and row_repeat > 0:
                if parser == "bs4":
                    scraped_data = self.bs_scrap_price(row_url,
                            domain, price_tag_name, price_attr_name, price_tag_name_2,
                            price_attr_values, title_tag_name, title_attr_name,
                            title_attr_value)
                    price, product_title = scraped_data
                    if price is not False:
                        result = self.price_check(price, product_title,
                                            row_price, row_email, row_url)
                    else:
                        result = ["", str(product_title)]
                        print(f'{Fore.RED}{result[1]}{Style.RESET_ALL}\n')
                elif parser == "selenium":
                    scraped_data = self.selenium_scrap_price(row_url,
                            domain, price_attr_values,
                            title_attr_value)
                    price, product_title = scraped_data
                    if price is not False:
                        result = self.price_check(price, product_title,
                                            row_price, row_email, row_url)
                    else:
                        result = ["", str(product_title)]
                        print(f'{Fore.RED}{result[1]}{Style.RESET_ALL}\n')
                else:
                    result = ["", 'The parser is wrong']
                    print(f'{Fore.RED}The parser is wrong'
                                f'{Style.RESET_ALL}\n')
                
                if result[0] == "cheap":
                    self.ws.update_cell(row, 5, row_repeat - 1)
                    self.ws.update_cell(row, 6, result[1])
                    print(f'{Fore.GREEN}{result[1]}{Style.RESET_ALL}\n')
                elif result[0] == "expensive":
                    self.ws.update_cell(row, 6, result[1])
                    print(f'{Fore.MAGENTA}{result[1]}{Style.RESET_ALL}\n')
                else:
                    self.ws.update_cell(row, 6, result[1])
                    print(f'{Fore.RED}{result[1]}{Style.RESET_ALL}\n')
            else:
                self.ws.update_cell(row, 6, error)
                print(f'{Fore.RED}{error}{Style.RESET_ALL}\n')
            
        self.disconnect_smtp()

    def gspread_data_checker(self, values):
        error = []
        row_url = ''
        row_price = 0
        row_email = ''
        row_repeat = 1
        domain = ''
        if len(values) >= 5:
            row_number = values[0]
            print(f'Row #{Style.BRIGHT}{row_number}{Style.RESET_ALL}')

            if values[1]:
                row_url = values[1]
            else:
                error.append("The url field is empty")

            mo = self.regex_domain.search(row_url)
            if mo is None: # check if url is not apropriet to the our regex_domain
                error.append("The bot doesn't support url of your shop")
            else:
                # the domain of the url for the Host header in the request
                # and to check that domain is on our base
                domain = mo.group()

            if domain not in self.my_dict:
                error.append("Your shop is not in our domain database")

            try:
                row_price = float(values[2].replace(',', '.'))
            except:
                error.append('The price must be integer or float')

            if (re.search(self.regex_email, values[3])):
                row_email = values[3]
            else:
                error.append('Wrong email')

            try:
                row_repeat = int(values[4])
            except:
                error.append('The repeat number must be integer')

            if not (re.search(self.regex_url, row_url)):
                error.append('The url should start from http:// or https://')
            
        else:
            error.append('Some fields are empty')

        return {'error': error, 'row_url': row_url,
                'domain': domain, 'row_price': row_price,
                'row_email': row_email, 'row_repeat': row_repeat}

    def read_gspread_url_database(self):
        # use creds to create a client to interact with the Google Drive API
        scope = ['https://spreadsheets.google.com/feeds']
        creds = ServiceAccountCredentials.from_json_keyfile_name(
           os.environ['GOOGLE_APPLICATION_CREDENTIALS'], scope)
        client = gspread.authorize(creds)
        # work with spreadsheet
        wb = client.open_by_url('https://docs.google.com/spreadsheets/d/1Cv'
                                '-zzL2YXqEizoH-ewQ0athDOtcjDL_T9xfNbc2YzUE/'
                                'edit#gid=0')
        self.ws = wb.worksheet('list')
        self.max_row_ws = len(self.ws.get_all_values())

    def open_keys_json(self):
        # open our json file with dict of domains and lists of tags which
        # we use to find elements on the page, check domain
        with open('keys.json', 'r') as my_keys:
            self.my_dict = json.load(my_keys)

    def smtp_connect(self):
        self.smtpObj = smtplib.SMTP('smtp.gmail.com', 587)
        self.smtpObj.ehlo()
        self.smtpObj.starttls()
        self.smtpObj.login('rivne.price.tracker@gmail.com', os.environ['rivne_price_tracker_password'])

    def send_email(self, email, shop_link, product_title, your_price, price):
        subject_text = 'Price of your good was reached your limit!!!'
        message_text = (f'The price of {product_title} at {shop_link} is {price} that '
                        f'less than your price - {your_price}!!!')
        message = f'Subject:{subject_text}\n\n{message_text}'
        self.smtpObj.sendmail('rivne.price.tracker@gmail.com',
                              email, message)

    def disconnect_smtp(self):
        self.smtpObj.quit()

    def pause_of_iterations(self, rest_time):
        sleep_time = round(rest_time / 60)
        print(f'{Fore.YELLOW}Next iteration will start in {sleep_time} minutes{Style.RESET_ALL}')
        time.sleep(rest_time)


reebok_price = PriceTracker()

iteration_number = 0
while True:
    iteration_number += 1
    print(f'\n{Style.BRIGHT}{Fore.YELLOW}Iteration #{iteration_number}{Style.RESET_ALL}\n')
    reebok_price.smtp_connect()
    reebok_price.open_keys_json()
    reebok_price.read_gspread_url_database()
    reebok_price.parse_shop_list()
    rest_time = random.randint(3600, 10800)
    reebok_price.pause_of_iterations(rest_time)
