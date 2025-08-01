# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import logging
import newspaper
import requests

from aiohttp import web
from bs4 import BeautifulSoup
from contextlib import suppress
from ipaddress import ip_address
from lxml import etree, html
from newspaper.article import ArticleDownloadState
from urllib.parse import urlparse

# Blocked image types
BLOCKED_IMG_TYPES = {"gif", "apng", "webp", "avif", "mng", "flif"}


class WebService:
    # Static class variables for the keys in app_routes
    HOME_KEY, COOKIE_KEY, EDIT_KEY, ABOUT_KEY, REST_KEY = "home", "cookies", "edit", "about", "rest"
    EXPORT_PDF_KEY, EXPORT_NAV_KEY, EXPORT_AFB_KEY, STATIC_KEY = "export_pdf", "export_nav", "export_afb", "static"
    HOW_IT_WORKS_KEY, WHAT_TO_SUBMIT_KEY = "how_it_works", "what_to_submit"
    REPORT_PARAM = "file"
    # Variations of punctuation we want to note
    HYPHENS = [
        "-",
        "\u058a",
        "\u05be",
        "\u2010",
        "\u2011",
        "\u2012",
        "\u2013",
        "\u2014",
        "\u2015",
        "\u2e3a",
        "\u2e3b",
        "\ufe5b",
        "\ufe63",
        "\uff0d",
    ]
    PERIODS = [".", "\ufe52", "\uff0e"]
    QUOTES = [
        '"',
        "''",
        "\u02ba",
        "\u02dd",
        "\u02ee",
        "\u02f6",
        "\u05f2",
        "\u05f4",
        "\u201c",
        "\u201d",
        "\u201f",
        "\u2033",
        "\u2036",
        "\u3003",
        "\uff02",
        "\u275d",
        "\u275e",
    ]
    BULLET_POINTS = ["\u2022", "\u2023", "\u2043", "\u2219", "\u25cb", "\u25cf", "\u25e6", "\u30fb"]

    def __init__(self, route_prefix=None, is_local=True):
        self.is_local = is_local
        self.cached_responses = dict()
        # A dictionary keeping track of the possible report categories
        self.categories_dict = dict()
        # Initialise app route info
        self.__app_routes = self._initialise_route_values(route_prefix_param=route_prefix)
        self.app = None

    def _initialise_route_values(self, route_prefix_param=None):
        """Function to initialise the web app's route values and return them as a dictionary."""
        # No route prefix by default, specify a home route here separately to prevent '/<route_prefix_param>/' suffix
        route_prefix, home_route = "", "/"
        if route_prefix_param is not None:
            # If we have a route prefix, update the prefix and home_route variables
            route_prefix = "/" + route_prefix_param
            home_route = route_prefix
        routes = {
            self.HOME_KEY: home_route,
            self.COOKIE_KEY: route_prefix + "/cookies",
            self.EDIT_KEY: route_prefix + "/edit/{%s}" % self.REPORT_PARAM,
            self.ABOUT_KEY: route_prefix + "/using-thread",
            self.REST_KEY: route_prefix + "/rest",
            self.EXPORT_PDF_KEY: route_prefix + "/export/pdf/{%s}" % self.REPORT_PARAM,
            self.EXPORT_NAV_KEY: route_prefix + "/export/nav/{%s}" % self.REPORT_PARAM,
            self.EXPORT_AFB_KEY: route_prefix + "/export/afb/{%s}" % self.REPORT_PARAM,
            self.HOW_IT_WORKS_KEY: route_prefix + "/how-thread-works",
            self.STATIC_KEY: route_prefix + "/theme/",
        }
        if not self.is_local:
            routes.update({self.WHAT_TO_SUBMIT_KEY: route_prefix + "/what-to-submit"})
        return routes

    def set_internal_app(self, app):
        self.app = app

    def get_route(self, route_key, param=None):
        """Function to get one of the web app's routes with the option of a parameter to be placed in the link."""
        try:
            route = self.__app_routes[route_key]
            if param is None:
                return route
            return route.replace("{%s}" % self.REPORT_PARAM, str(param))
        # If the method doesn't receive a valid key, return None
        except KeyError:
            return None

    def check_and_clear_cached_responses(self):
        if len(self.cached_responses) > 100:
            self.cached_responses = dict()

    async def _call_app_method(
        self,
        request,
        *args,
        method_name=None,
        return_val_when_local=None,
        return_val_on_error=None,
        **kwargs,
    ):
        """Function to call an app-method given its name."""
        if self.is_local:
            # Not applicable to local setups
            return return_val_when_local

        try:
            # Attempt to use app's method; log if this couldn't be done
            app_method = getattr(request.app if request else self.app, method_name)
            return await app_method(*args, **kwargs)

        except Exception as e:
            logging.error(f"Misconfigured app: {method_name}() error: {e}")
            return return_val_on_error

    async def action_allowed(self, request, action, context=None):
        """Function to check an action is permitted given a request."""
        if self.is_local:
            # A permission-checker is not implemented for local-use
            # and the user is in control of all their data, so allow the action
            return True

        try:
            # Attempt to use app's method to check permission; log if this couldn't be done
            return await request.app.permission_checker(request, action, context)

        except (TypeError, AttributeError) as e:
            logging.error(f"Misconfigured app: permission_checker() error: {e}")
            raise web.HTTPInternalServerError()

    async def url_allowed(self, request, url):
        """Function to check a URL is allowed to be submitted."""
        if self.is_local:
            # A URL-checker is not implemented for local-use so allow the action
            return True

        try:
            # Attempt to use app's method to check URL; log if this couldn't be done
            return await request.app.url_checker(request, url)

        except (TypeError, AttributeError) as e:
            logging.error(f"Misconfigured app: url_checker() error: {e}")
            raise SystemError("Apologies, this URL could not be processed at this time, please contact us.")

    async def on_report_complete(self, request, report_data):
        """Function to complete any post-complete actions for a report."""
        return await self._call_app_method(
            request,
            request,
            report_data,
            method_name="on_report_complete",
        )

    async def on_report_error(self, request, log_error):
        """Function to complete any submission-error actions for a report."""
        return await self._call_app_method(
            request,
            log_error,
            method_name="on_report_submission_error",
        )

    async def on_attack_name_change(self, attack_id, attack_name):
        """Function to complete any post-update actions for an attack."""
        return await self._call_app_method(
            None,
            attack_id,
            attack_name,
            method_name="on_attack_name_change",
        )

    async def get_current_arachne_user(self, request):
        """Function to obtain the current Arachne username and token given a request."""
        return await self._call_app_method(
            request,
            request,
            method_name="get_current_arachne_user",
            return_val_when_local=(None, None),
            return_val_on_error=(None, None),
        )

    async def auto_gen_data_is_valid(self, request, request_data) -> bool:
        """Function to confirm data for an automatically-generated report is valid."""
        return await self._call_app_method(
            request,
            request,
            request_data,
            method_name="auto_gen_data_is_valid",
            return_val_when_local=True,
            return_val_on_error=False,
        )

    async def map_all_html(self, url_input, sentence_limit=None):
        a = newspaper.Article(url_input, keep_article_html=True)
        a.config.MAX_TEXT = None
        a.download()
        if a.download_state != ArticleDownloadState.SUCCESS:
            return None, None
        a.parse()
        if not a.text:  # HTML may have been retrieved but if there is no text, ignore this url
            return None, None
        results, plaintext, images, seen_images = [], [], [], []
        images = await self._collect_all_images(a.images)
        plaintext = await self._extract_text_as_list(a.text)
        html_elements, htmltags, htmltext = self._extract_html_as_list(a.article_html)
        text_count = 0

        # Loop through pt one by one, matching its line with a forward-advancing pointer on the html
        counter = 0
        for pt in plaintext:
            text_match_found = False
            image_found = False
            # Loop through the html elements to process images and text (if we didn't find the plaintext)
            for forward_advancer in range(counter, len(html_elements)):
                if "src=" in html_elements[forward_advancer] and image_found is False:
                    # Found an image, put it in data but don't advance in case there's text.
                    soup = BeautifulSoup(html_elements[forward_advancer], "html.parser")
                    current_images = soup.findAll("img")
                    for cur_img in current_images:
                        try:
                            source = cur_img["src"]
                        # All img tags should have a src attribute. In case this one doesn't, there is no image to save
                        except KeyError:
                            continue
                        # If no source was obtained or this image is a blocked filetype: continue
                        if not source or any(source.lower().endswith(img_type) for img_type in BLOCKED_IMG_TYPES):
                            continue
                        img_dict = await self._match_and_construct_img(images, source)
                        if source not in seen_images:
                            results.append(img_dict)
                            seen_images.append(source)
                            image_found = True
                for temp in [pt, pt.strip()]:
                    if temp == htmltext[forward_advancer]:
                        # Found the matching word, put the text into the data.
                        results.append(self._construct_text_dict(temp, htmltags[forward_advancer]))
                        counter = forward_advancer + 1
                        text_match_found = True
                        break
                if text_match_found:
                    break
            # Tidy up depending on if images or text were found
            if not text_match_found:
                if image_found:
                    # Didn't find matching text, but found an image. Image is misplaced.
                    seen_images = seen_images[:-1]
                    results = results[:-1]
                else:
                    # Add this missing text with default <p> tag
                    results.append(self._construct_text_dict(pt, "p"))
                    text_match_found = True
            if text_match_found:
                text_count += 1
            if sentence_limit and (text_count >= sentence_limit):
                break
        return results, a

    async def build_final_html(self, original_html, sentences):
        """Function to merge and return html and sentence data for outputting a report: html and sentences should be
        in order of elem_index and sen_index respectively."""
        final_html = []
        # The index we are up to for iterating the html list
        latest_html_idx = 0
        # The images added to the final-merged-html
        added_image_ids = set()
        # Looping through each sentence...
        for sentence_data in sentences:
            found_sentence = False  # flag to track if found in html-list
            final_html_subset = []  # temp-list that may be added to final_html
            temp_added_image_ids = set()  # temp-set of images potentially added to final_html
            # Loop through html-list from last-matching position
            for e_idx, element in enumerate(original_html[latest_html_idx:]):
                # If there is an image, add it to temp-lists to potentially be added
                if element["tag"] == "img" and element["uid"] not in added_image_ids:
                    final_html_subset.append(self._build_final_image_dict(element))
                    temp_added_image_ids.add(element["uid"])
                # If we found the sentence, complete the temp-list with this sentence and break from this loop
                elif sentence_data["html"] in element["text"]:
                    final_html_subset.append(self._build_final_html_text(sentence_data, element["tag"]))
                    latest_html_idx = latest_html_idx + e_idx
                    found_sentence = True
                    break
            # If the sentence was found, the temp list can be added to the final list; update added_image_ids too
            if found_sentence:
                final_html += final_html_subset
                added_image_ids.update(temp_added_image_ids)
            # If the sentence was not found, add it as a <p> to final list to preserve order of the sentences
            # Disregard any images (in final_html_subset) as this may be out of order
            else:
                final_html.append(self._build_final_html_text(sentence_data, "p"))
        # Just in case we missed any images, add them at the end
        for element in original_html:
            if element["tag"] == "img" and element["uid"] not in added_image_ids:
                final_html.append(self._build_final_image_dict(element))
                added_image_ids.add(element["uid"])
        return final_html

    @staticmethod
    async def remove_html_markup_and_found(s):
        tag = False
        quote = False
        out = ""
        for c in s:
            if c == "<" and not quote:
                tag = True
            elif c == ">" and not quote:
                tag = False
            elif (c == '"' or c == "'") and tag:
                quote = not quote
            elif not tag:
                out = out + c
        sep = "!FOUND:"
        out = out.split(sep, 1)[0]
        return out.strip().replace("\n", " ")

    async def get_url(self, url, returned_format=None):
        if returned_format == "html":
            logging.info("[!] HTML support is being refactored. Currently data is being returned plaintext")
        r = self.get_response_from_url(url)
        # Use the response text to get contents for this url
        b = newspaper.fulltext(r.text)
        return str(b).replace("\n", "<br>") if b else None

    def get_response_from_url(self, url, log_errors=True, allow_error=True):
        """Function to return a request Response object from a given URL."""
        # Retrieve a cached response for this URL
        self.check_and_clear_cached_responses()
        cached = self.cached_responses.get(url)
        if cached is not None:
            return cached

        try:
            with requests.get(url) as response:
                response_clone = requests.Response()
                response_clone.status_code = response.status_code
                response_clone.headers = response.headers
                response_clone._content = response.content
                response_clone.encoding = response.encoding
                response_clone.url = response.url

                self.cached_responses[url] = response_clone
                return response_clone
        except requests.exceptions.ConnectionError as e:
            if log_errors:
                logging.error(f"URL retrieval failure: {e}")

            if not allow_error:
                raise e

    def urls_match(self, testing_url="", matches_with=""):
        """Function to check if two URLs are the same."""
        # Quick initial check that both strings are identical
        if testing_url == matches_with:
            return True
        # Handle any redirects (e.g. https redirects; added '/'s at the end of a url)
        req1 = self.get_response_from_url(testing_url, log_errors=False)
        req2 = self.get_response_from_url(matches_with, log_errors=False)
        if not req1.url:
            raise ValueError("A URL has not been specified")
        if req1.url == req2.url:
            return True
        # There can be many further things to check here (e.g. https://stackoverflow.com/questions/5371992)
        # but leaving as this for now
        return False

    async def verify_url(self, request, url=""):
        """Function to check a URL can be parsed. Returns None if successful."""
        url_error = "Unable to parse URL %s" % url
        # Check the url can be parsed by the urllib module
        try:
            parsed_url = urlparse(url)
            # Allow the url if it has a scheme and hostname
            accept_url = all([parsed_url.scheme, parsed_url.netloc, parsed_url.hostname])
        except ValueError:  # Raise an error if the url could not be parsed
            raise ValueError(url_error)
        if not accept_url:  # Raise an error if the url could be parsed but does not have sufficient components
            raise ValueError(url_error)
        try:
            # Check the URL is allowed
            await self.url_allowed(request, url)
            # Check a request-response can be retrieved from this url
            self.get_response_from_url(url, log_errors=False, allow_error=False)
        except requests.exceptions.ConnectionError:
            raise ValueError(url_error)
        # Check the url does not contain an IP address
        created_ip = None
        with suppress(ValueError):
            created_ip = ip_address(parsed_url.hostname)
        if created_ip:  # Raise an error if an IP address object was successfully created from the url's hostname
            raise ValueError(url_error)

    @staticmethod
    def _build_final_image_dict(element):
        final_element = dict()
        final_element["uid"] = element["uid"]
        final_element["text"] = element["text"]
        final_element["tag"] = element["tag"]
        final_element["found_status"] = element["found_status"]
        return final_element

    @staticmethod
    def _build_final_html_text(sentence, tag):
        final_element = dict()
        final_element["uid"] = sentence["uid"]
        final_element["text"] = sentence["text"]
        final_element["tag"] = tag
        final_element["found_status"] = sentence["found_status"]
        final_element["is_ioc"] = sentence["is_ioc"]
        return final_element

    @staticmethod
    async def _collect_all_images(image_set):
        images = []
        for image in image_set:
            images.append(image)
        return images

    @staticmethod
    async def _extract_text_as_list(plaintext_doc):
        plaintext = []
        for pt_line in plaintext_doc.split("\n"):
            if pt_line != "":
                plaintext.append(pt_line)
        return plaintext

    @staticmethod
    def _extract_html_as_list(html_doc):
        """Get list of html data given a html string.
        :param html_doc: the html string.
        :return: Three lists: 1. the list of html elements as strings.
                2. the tag of each html element.
                3. the list of texts for each html element.
                Each list will be the same length.
        """
        # Get the html element object based on the provided string
        html_parsed = html.fromstring(html_doc)
        # Keep all elements that have child nodes, have text or are images
        filtered = [element for element in html_parsed if element.text or len(element) or element.tag == "img"]
        # Set up the three lists for the elements, tags and text
        html_elements, html_tags_list, html_text_list = [], [], []
        # Iterate through each element and populate the three lists
        for element in filtered:
            # element as string including the tags
            element_as_text = etree.tostring(element, method="html").decode()
            html_elements.append(element_as_text)
            # element's text content (without tags)
            html_text_list.append(str(element.text_content()).strip())
            # Thread currently supports these types of tags, populate the tag list with one of these
            if "<h" in element_as_text:
                html_tags_list.append("header")
            elif "<li" in element_as_text:
                html_tags_list.append("li")
            else:
                html_tags_list.append("p")
        # Return the three lists
        return html_elements, html_tags_list, html_text_list

    @staticmethod
    async def _match_and_construct_img(images, source):
        for i in range(0, len(images)):
            if source in images[i]:
                source = images[i]
        img_dict = dict()
        img_dict["text"] = source
        img_dict["tag"] = "img"
        img_dict["ml_techniques_found"] = []
        img_dict["reg_techniques_found"] = []
        return img_dict

    @staticmethod
    def _construct_text_dict(plaintext, tag):
        res_dict = dict()
        res_dict["text"] = plaintext
        res_dict["tag"] = tag
        res_dict["ml_techniques_found"] = []
        res_dict["reg_techniques_found"] = []
        return res_dict
