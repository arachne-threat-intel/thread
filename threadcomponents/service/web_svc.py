# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import asyncio
import logging
import newspaper
import nltk
import re
import requests

from aiohttp import web
from bs4 import BeautifulSoup
from contextlib import suppress
from html2text import html2text
from ipaddress import ip_address
from lxml import etree, html
from newspaper.article import ArticleDownloadState
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from urllib.parse import urlparse

# Abbreviated words for sentence-splitting
ABBREVIATIONS = {'dr', 'vs', 'mr', 'mrs', 'ms', 'prof', 'inc', 'fig', 'e.g', 'i.e', 'u.s'}
# Blocked image types
BLOCKED_IMG_TYPES = {'gif', 'apng', 'webp', 'avif', 'mng', 'flif'}

# Regular expressions of hashes for indicators of compromise
MD5_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{32})(?:[^a-fA-F\d]|\b)")
SHA1_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{40})(?:[^a-fA-F\d]|\b)")
SHA256_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{64})(?:[^a-fA-F\d]|\b)")
SHA512_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{128})(?:[^a-fA-F\d]|\b)")
IPV4_REGEX = re.compile(r"""
        (?:^|
            (?![^\d\.])
        )
        (
            (?:
                (?:[1-9]?\d|1\d\d|2[0-4]\d|25[0-5])
                [\[\(\\]*?\.[\]\)]*?
            ){3}
            (?:[1-9]?\d|1\d\d|2[0-4]\d|25[0-5])
        )
        (?:(?=[^\d\.])|$)
    """, re.VERBOSE)
IPV6_REGEX = re.compile(r"\b((?:[a-f0-9]{1,4}:|:){2,7}(?:[a-f0-9]{1,4}|:))\b", re.IGNORECASE | re.VERBOSE)


class WebService:
    """A class for website-related tasks."""
    # Static class variables for the keys in app_routes
    HOME_KEY, COOKIE_KEY, EDIT_KEY, ABOUT_KEY, REST_KEY = 'home', 'cookies', 'edit', 'about', 'rest'
    EXPORT_PDF_KEY, EXPORT_NAV_KEY, STATIC_KEY = 'export_pdf', 'export_nav', 'static'
    HOW_IT_WORKS_KEY, WHAT_TO_SUBMIT_KEY = 'how_it_works', 'what_to_submit'
    REPORT_PARAM = 'file'
    # Variations of punctuation we want to note
    HYPHENS = ['-', u'\u058A', u'\u05BE', u'\u2010', u'\u2011', u'\u2012', u'\u2013', u'\u2014', u'\u2015', u'\u2E3A',
               u'\u2E3B', u'\uFE5B', u'\uFE63', u'\uFF0D']
    PERIODS = ['.', u'\uFE52', u'\uFF0E']
    QUOTES = ['"', "''", u'\u02BA', u'\u02DD', u'\u02EE', u'\u02F6', u'\u05F2', u'\u05F4', u'\u201C', u'\u201D',
              u'\u201F', u'\u2033', u'\u2036', u'\u3003', u'\uFF02', u'\u275D', u'\u275E']
    BULLET_POINTS = [u'\u2022', u'\u2023', u'\u2043', u'\u2219', u'\u25CB', u'\u25CF', u'\u25E6', u'\u30fb']

    def __init__(self, route_prefix=None, is_local=True):
        self.is_local = is_local
        self.tokenizer_sen = None
        self.cached_responses = dict()
        # A dictionary keeping track of the possible report categories
        self.categories_dict = dict()
        # Initialise app route info
        self.__app_routes = self._initialise_route_values(route_prefix_param=route_prefix)

    def _initialise_route_values(self, route_prefix_param=None):
        """Function to initialise the web app's route values and return them as a dictionary."""
        # No route prefix by default, specify a home route here separately to prevent '/<route_prefix_param>/' suffix
        route_prefix, home_route = '', '/'
        if route_prefix_param is not None:
            # If we have a route prefix, update the prefix and home_route variables
            route_prefix = '/' + route_prefix_param
            home_route = route_prefix
        routes = {
            self.HOME_KEY: home_route, self.COOKIE_KEY: route_prefix + '/cookies',
            self.EDIT_KEY: route_prefix + '/edit/{%s}' % self.REPORT_PARAM,
            self.ABOUT_KEY: route_prefix + '/using-thread', self.REST_KEY: route_prefix + '/rest',
            self.EXPORT_PDF_KEY: route_prefix + '/export/pdf/{%s}' % self.REPORT_PARAM,
            self.EXPORT_NAV_KEY: route_prefix + '/export/nav/{%s}' % self.REPORT_PARAM,
            self.HOW_IT_WORKS_KEY: route_prefix + '/how-thread-works',
            self.STATIC_KEY: route_prefix + '/theme/'
        }
        if not self.is_local:
            routes.update({self.WHAT_TO_SUBMIT_KEY: route_prefix + '/what-to-submit'})
        return routes

    def get_route(self, route_key, param=None):
        """Function to get one of the web app's routes with the option of a parameter to be placed in the link."""
        try:
            route = self.__app_routes[route_key]
            if param is None:
                return route
            return route.replace('{%s}' % self.REPORT_PARAM, str(param))
        # If the method doesn't receive a valid key, return None
        except KeyError:
            return None

    def initialise_tokenizer(self):
        self.tokenizer_sen = nltk.data.load('tokenizers/punkt/english.pickle')
        try:
            self.tokenizer_sen._params.abbrev_types.update(ABBREVIATIONS)
        except AttributeError:
            pass

    def clear_cached_responses(self):  # TODO consider how often to call this
        self.cached_responses = dict()

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
            logging.error('Misconfigured app: permission_checker() error: ' + str(e))
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
            logging.error('Misconfigured app: url_checker() error: ' + str(e))
            # SystemError makes more sense but we are listening for ValueErrors
            raise ValueError('Apologies, this URL could not be processed at this time, please contact us.')

    async def on_report_complete(self, request, report_data):
        """Function to complete any post-complete actions for a report."""
        if self.is_local:
            # No post-complete actions needed for local-use
            return
        try:
            # Attempt to use app's on-complete method; log if this couldn't be done
            return await request.app.on_report_complete(request, report_data)
        except (TypeError, AttributeError) as e:
            logging.error('Misconfigured app: on_report_complete() error: ' + str(e))

    async def get_current_arachne_user(self, request):
        """Function to obtain the current Arachne username and token given a request."""
        if self.is_local:
            return None, None
        try:
            # Attempt to use app's method to obtain the username & token; log if this couldn't be done
            return await request.app.get_current_arachne_user(request)
        except (TypeError, AttributeError) as e:
            logging.error('Misconfigured app: get_current_arachne_user() error: ' + str(e))
            return None, None

    async def auto_gen_data_is_valid(self, request, request_data) -> bool:
        """Function to confirm data for an automatically-generated report is valid."""
        if self.is_local:
            return True
        try:
            return await request.app.auto_gen_data_is_valid(request, request_data)
        except Exception as e:
            logging.error('Misconfigured app: auto_gen_data_is_valid() error: ' + str(e))
        return False

    async def map_all_html(self, url_input, sentence_limit=None):
        """Function to return the HTML and Newspaper-article for a given URL."""
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
                if 'src=' in html_elements[forward_advancer] and image_found is False:
                    # Found an image, put it in data but don't advance in case there's text.
                    soup = BeautifulSoup(html_elements[forward_advancer], 'html.parser')
                    current_images = soup.findAll('img')
                    for cur_img in current_images:
                        try:
                            source = cur_img['src']
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
                    results.append(self._construct_text_dict(pt, 'p'))
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
                if element['tag'] == 'img' and element['uid'] not in added_image_ids:
                    final_html_subset.append(self._build_final_image_dict(element))
                    temp_added_image_ids.add(element['uid'])
                # If we found the sentence, complete the temp-list with this sentence and break from this loop
                elif sentence_data['html'] in element['text']:
                    final_html_subset.append(self._build_final_html_text(sentence_data, element['tag']))
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
                final_html.append(self._build_final_html_text(sentence_data, 'p'))
        # Just in case we missed any images, add them at the end
        for element in original_html:
            if element['tag'] == 'img' and element['uid'] not in added_image_ids:
                final_html.append(self._build_final_image_dict(element))
                added_image_ids.add(element['uid'])
        return final_html

    def __rejoin_defanged(self, sentences):
        """
        There are times when the [dot] mistakenly splits a defanged IP/domain.
        If this is the case, rejoin them in one sentence.
        """
        corrected_sentences = []
        previous_sentence = sentences[0]

        # Don't continue if there aren't later sentences to compare to
        if not sentences[1:]:
            return sentences

        for idx, sentence in enumerate(sentences[1:]):
            if previous_sentence.endswith('[.') and sentence.startswith(']'):
                previous_sentence += sentence
                if idx == len(sentences) - 2:
                    corrected_sentences.append(previous_sentence)
            else:
                corrected_sentences.append(previous_sentence)
                previous_sentence = sentence
        
        return corrected_sentences
    
    def __split_by_hash(self, sentences):
        """
        Split sentences containing a hash.
        """
        splitted_by_md5 = []
        for sentence in sentences:
            splitted_by_md5 += MD5_REGEX.split(sentence)
        
        splitted_by_sha1 = []
        for sentence in splitted_by_md5:
            splitted_by_sha1 += SHA1_REGEX.split(sentence)
        
        splitted_by_sha256 = []
        for sentence in splitted_by_sha1:
            splitted_by_sha256 += SHA256_REGEX.split(sentence)
        
        splitted_by_sha512 = []
        for sentence in splitted_by_sha256:
            splitted_by_sha512 += SHA512_REGEX.split(sentence)
        
        return splitted_by_sha512
    
    def __split_by_url(self, sentences):
        """
        Split sentences containing a URL.
        """
        return sentences
    
    def __split_by_ip(self, sentences):
        """
        Split sentences containing an IP address.
        """
        splitted_by_ipv4 = []
        for sentence in sentences:
            splitted_by_ipv4 += IPV4_REGEX.split(sentence)
        
        splitted_by_ipv6 = []
        for sentence in splitted_by_ipv4:
            splitted_by_ipv6 += IPV6_REGEX.split(sentence)

        return splitted_by_ipv6
    
    def __correct_sentences(self, sentences):
        """
        Correct sentence splitting.
        """
        rejoined_sentences = self.__rejoin_defanged(sentences)
        sentences_split_by_hash = self.__split_by_hash(rejoined_sentences)
        sentences_split_by_url = self.__split_by_url(sentences_split_by_hash)
        sentences_split_by_ip = self.__split_by_ip(sentences_split_by_url)

        return sentences_split_by_ip
    
    def tokenize_sentence(self, data, sentence_limit=None):
        """
        :criteria: expects a dictionary of this structure:
        """
        html_sentences = self.tokenizer_sen.tokenize(data)
        corrected_html_sentences = set(self.__correct_sentences(html_sentences))

        sentences = []
        for current in corrected_html_sentences:
            if sentence_limit and (len(sentences) >= sentence_limit):
                break
            # Further split by break tags as this might misplace highlighting in the front end
            no_breaks = set([x for x in current.split('<br>') if x])
            for fragment in no_breaks:
                sentence_data = dict()
                sentence_data['html'] = fragment
                sentence_data['text'] = html2text(fragment)
                sentence_data['ml_techniques_found'] = []
                sentence_data['reg_techniques_found'] = []
                sentences.append(sentence_data)
        return sentences

    @staticmethod
    async def tokenize(s):
        """Function to remove stopwords from a sentence and return a list of words to match"""
        word_list = re.findall(r'\w+', s.lower())
        filtered_words = [word for word in word_list if word not in stopwords.words('english')]
        """Perform NLP Lemmatization and Stemming methods"""
        lemmed = []
        stemmer = SnowballStemmer('english')
        for i in filtered_words:
            await asyncio.sleep(0.001)
            lemmed.append(stemmer.stem(str(i)))
        return ' '.join(lemmed)

    @staticmethod
    async def remove_html_markup_and_found(s):
        tag = False
        quote = False
        out = ""
        for c in s:
            if c == '<' and not quote:
                tag = True
            elif c == '>' and not quote:
                tag = False
            elif (c == '"' or c == "'") and tag:
                quote = not quote
            elif not tag:
                out = out + c
        sep = '!FOUND:'
        out = out.split(sep, 1)[0]
        return out.strip().replace('\n', ' ')

    async def get_url(self, url, returned_format=None):
        if returned_format == 'html':
            logging.info('[!] HTML support is being refactored. Currently data is being returned plaintext')
        r = self.get_response_from_url(url)
        # Use the response text to get contents for this url
        b = newspaper.fulltext(r.text)
        return str(b).replace('\n', '<br>') if b else None

    def get_response_from_url(self, url, log_errors=True, allow_error=True):
        """Function to return a request Response object from a given URL."""
        # Retrieve a cached response for this URL
        cached = self.cached_responses.get(url)
        if cached is not None:
            return cached
        # Specify if we retry retrieving a response on failure
        retry_on_fail = True
        # Flag if we can close the connection once we are finished
        close_conn = True
        try:
            r = requests.get(url)
        except requests.exceptions.ConnectionError as conn_error:
            # Log error if requested
            if log_errors:
                logging.error('URL connection failure: ' + str(conn_error))
            # Raise the error if requested
            if not allow_error:
                raise conn_error
            # If the URL could not be retrieved due to a raised Error, build a new Response object and skip retrying
            r = requests.models.Response()
            r.status_code = 418
            retry_on_fail = False
            close_conn = False
        if retry_on_fail and not r.ok:
            # If the request response is not good, close the current connection and replace with a prepared request
            r.close()
            sess = requests.Session()
            r = requests.Request('GET', url)
            prep = r.prepare()
            r = sess.send(prep)
        if not r.ok and log_errors:
            logging.error('URL retrieval failed with code ' + str(r.status_code))
        if close_conn:
            r.close()
        # Cache the response object for this URL
        self.cached_responses[url] = r
        return r

    def urls_match(self, testing_url='', matches_with=''):
        """Function to check if two URLs are the same."""
        # Quick initial check that both strings are identical
        if testing_url == matches_with:
            return True
        # Handle any redirects (e.g. https redirects; added '/'s at the end of a url)
        req1 = self.get_response_from_url(testing_url, log_errors=False)
        req2 = self.get_response_from_url(matches_with, log_errors=False)
        if not req1.url:
            raise ValueError('A URL has not been specified')
        if req1.url == req2.url:
            return True
        # There can be many further things to check here (e.g. https://stackoverflow.com/questions/5371992)
        # but leaving as this for now
        return False

    async def verify_url(self, request, url=''):
        """Function to check a URL can be parsed. Returns None if successful."""
        url_error = 'Unable to parse URL %s' % url
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
        final_element['uid'] = element['uid']
        final_element['text'] = element['text']
        final_element['tag'] = element['tag']
        final_element['found_status'] = element['found_status']
        return final_element

    @staticmethod
    def _build_final_html_text(sentence, tag):
        final_element = dict()
        final_element['uid'] = sentence['uid']
        final_element['text'] = sentence['text']
        final_element['tag'] = tag
        final_element['found_status'] = sentence['found_status']
        final_element['is_ioc'] = sentence['is_ioc']
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
        for pt_line in plaintext_doc.split('\n'):
            if pt_line != '':
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
        filtered = [element for element in html_parsed if element.text or len(element) or element.tag == 'img']
        # Set up the three lists for the elements, tags and text
        html_elements, html_tags_list, html_text_list = [], [], []
        # Iterate through each element and populate the three lists
        for element in filtered:
            # element as string including the tags
            element_as_text = etree.tostring(element, method='html').decode()
            html_elements.append(element_as_text)
            # element's text content (without tags)
            html_text_list.append(str(element.text_content()).strip())
            # Thread currently supports these types of tags, populate the tag list with one of these
            if '<h' in element_as_text:
                html_tags_list.append('header')
            elif '<li' in element_as_text:
                html_tags_list.append('li')
            else:
                html_tags_list.append('p')
        # Return the three lists
        return html_elements, html_tags_list, html_text_list

    @staticmethod
    async def _match_and_construct_img(images, source):
        for i in range(0, len(images)):
            if source in images[i]:
                source = images[i]
        img_dict = dict()
        img_dict['text'] = source
        img_dict['tag'] = 'img'
        img_dict['ml_techniques_found'] = []
        img_dict['reg_techniques_found'] = []
        return img_dict

    @staticmethod
    def _construct_text_dict(plaintext, tag):
        res_dict = dict()
        res_dict['text'] = plaintext
        res_dict['tag'] = tag
        res_dict['ml_techniques_found'] = []
        res_dict['reg_techniques_found'] = []
        return res_dict
