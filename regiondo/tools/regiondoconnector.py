import requests
import time
import hashlib, hmac
import json


class RegiondoConnector:
    """ Connector to regiondo service """

    def __init__(self, public_key, private_key, accept_language):
        self.__public_key = public_key
        self.__private_key = private_key
        self.__accept_language = accept_language

    def call(self, request_method, request_path, request_parameters, base_url='https://api.regiondo.com/v1/'):
        # build uri parameters
        uri_parameters = ''
        for key in request_parameters:
            if uri_parameters:
                uri_parameters += '&'
            uri_parameters += str(key) + '=' + str(request_parameters[key])

        url = base_url + request_path + '?' + uri_parameters

        # build hash
        req_time = str(int(time.time()))
        message = req_time + self.__public_key + uri_parameters
        message_hash = hmac.new(bytes(self.__private_key, 'UTF-8'), message.encode(), hashlib.sha256).hexdigest()

        # build headers
        headers = {
            'X-API-ID': self.__public_key,
            'X-API-TIME': req_time,
            'X-API-HASH': message_hash,
            'Accept-Language': self.__accept_language
        }

        response = requests.request(request_method, url, headers=headers, data=request_parameters)
        try:
            return json.loads(response.text)
        except:
            return response.text




