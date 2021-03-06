from os import terminal_size

import re
import scrapy
from enum import Enum

from crimeparser.items import ReportItem, CrimeItem


class PoliceSpider(scrapy.Spider):
    name = "police"

    def start_requests(self):
        urls = [
            "https://www.polizei.sachsen.de/de/medieninformationen_pdd.htm"
        ]
        for url in urls:
            request = scrapy.Request(url=url, callback=self.parse)
            request.meta['dont_cache'] = True
            yield request

    def parse(self, response):
        links = response.css("div[id='presse'] a::attr(href)")
        for href in links:
            yield response.follow(href, self.parse_report)

    def parse_report(self, response):
        report_id = self.extract_unique_id(response.url)

        content = response.css("div[id='content']").get()
        parts = content.split("<br>")
        parts = [part.strip() for part in parts]
        parts = list(filter(None, parts))

        crime_parser = CrimeParser(parts)
        number, year = crime_parser.extract_number_and_year()
        crimes = crime_parser.extract_crimes()

        yield ReportItem(id=report_id, number=number, year=year, title=None, crimes=crimes)

    def extract_unique_id(self, url):
        temp = url.rpartition('.')[0]
        return temp.rpartition('/')[2]


class CrimeParser:

    def __init__(self, parts):
        self.__parts = parts

    def extract_number_and_year(self):
        for part in self.__parts:
            match = re.search("Medieninformation:(.*)/(.*)", part)
            if match:
                number = int(match.group(1).strip())
                year = int(match.group(2).strip())
                return number, year

        return None, None

    def extract_crimes(self):
        crimes = []

        state = ParserState.NONE
        title = []
        content = []
        region = None

        for part in self.__parts:
            # title are in strong tags, appeal for witnesses additionally in em tags
            if "<strong>" in part and not "<em>" in part:
                state = ParserState.TITLE
                self.__assemble_and_append_crime(crimes, title, content, region)

            text = self.__remove_tags(part)
            if self.__is_landkreis(text):
                region = text

            if state == ParserState.TITLE and not self.__is_landkreis(text):
                title.append(text)
            elif state == ParserState.CONTENT and '<ul class="verweisliste">' not in part:
                content.append(text)

            if "</strong>" in part:
                state = ParserState.CONTENT

        self.__assemble_and_append_crime(crimes, title, content, region)

        return crimes

    def __remove_tags(self, html_text):
        return re.sub("<.*?>", "", html_text).strip()

    def __is_landkreis(self, text):
        return (text == "Landeshauptstadt Dresden"
                or text == "Landkreis Meißen"
                or text == "Landkreis Sächsische Schweiz-Osterzgebirge")

    def __remove_prefix(self, text, prefix):
        if text.startswith(prefix):
            return text[len(prefix):]
        return text

    def __assemble_and_append_crime(self, crimes, title, content, region):
        if not (title and content):
            return

        time = None
        place = None
        for text in content[:]:
            time = self.__extract_text_after_prefix(time, text, "Zeit:", content)
            place = self.__extract_text_after_prefix(place, text, "Ort:", content)

        content_text = None
        if content:
            content_text = "\n".join(content)

        crimes.append(CrimeItem(title=title[0], time=time, place=place, content=content_text, region=region))
        title.clear()
        content.clear()

    def __extract_text_after_prefix(self, old_text, text, prefix, content):
        if text.startswith(prefix):
            old_text = text[len(prefix):].strip()
            content.remove(text)
        return old_text


class ParserState(Enum):
    NONE = 0
    TITLE = 1
    CONTENT = 2
