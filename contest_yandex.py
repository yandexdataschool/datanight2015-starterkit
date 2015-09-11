#!/usr/bin/env python

import json
import time
import requests
import unittest
import logging

URL_TOKEN = "https://oauth.yandex.ru/token"
URL_SUBMIT = "https://api.contest.yandex.net/anytask/submit"
URL_PROBLEMS = "https://api.contest.yandex.net/anytask/problems"
URL_RESULTS = "https://api.contest.yandex.net/anytask/results"
URL_PP = "/action/contest/{contestId}/list-problems?locale=ru"
CONTEST_ID = 1303
MAX_RETRIES = 10
RESULT_TIMEOUT = 30


class YaContestSubmitter(object):
    def __init__(self, code=None, oauth_token=None, contest_id=None):
        self.oauth = oauth_token
        self.contest_id = contest_id
        if oauth_token is None and code is not None:
            status, message, oauth = self.code2oauth_token(code)
            if status:
                self.oauth = oauth
        self.last_submit = None

    def _list_contest_problems(self, contest_id=None):
        assert self.contest_id is not None or contest_id is not None
        if contest_id is None:
            contest_id = self.contest_id
        result = requests.get(
            "{}?contestId={}&locale=ru".format(URL_PROBLEMS, contest_id))
        self._check_request_(result, "Get list of problems error")
        return json.loads(result.text)

    def _get_first_contest_problem(self):
        r = self._list_contest_problems()
        return r['result']['problems'][0]

    def code2oauth_token(self, code):
        '''
        code - code 7-digit number you get from 
            https://oauth.yandex.ru/authorize?response_type=code&client_id=2ae47301f8e64ae697c122edd7dde763
        '''
        if self.oauth is not None:
            message = "you already have access token"
            return True, message, self.oauth
        result = requests.post(
            URL_TOKEN,
            data={
                'grant_type': 'authorization_code',
                'client_id': '2ae47301f8e64ae697c122edd7dde763',
                'client_secret': 'a4d1256f2c3d4ddfa5fa83ec60862e59',
                'code': code
            })
        if not result.ok:
            message = "{} ({})".format(
                json.loads(result.text)['error'],
                json.loads(result.text)['error_description'])
            logging.error(message)
        else:
            self.oauth = json.loads(result.text)['access_token']
            message = "Success"
            logging.info("OAuth token: {}".format(self.oauth))
        return result.ok, message, self.oauth

    def _headers_(self):
        return {'Authorization': 'OAuth {}'.format(self.oauth)}

    def _check_request_(self, req, error_message):
        assert req.ok, "{}: {} ({})".format(
            error_message, 
            json.loads(req.text)['error']['message'],
            req.text)

    def submit(self, filename, contest_id=None):
        assert self.oauth is not None, "Get oauth token first"
        assert self.contest_id is not None or contest_id is not None, "Please specify contest_id"
        if contest_id is not None:
            self.contest_id = contest_id
        files = {'file': open(filename, 'rb')}
        problem_id = self._get_first_contest_problem()['id']
        result = None
        for n_try in xrange(MAX_RETRIES):
            req = requests.post(URL_SUBMIT,
                                data={
                                    'contestId': self.contest_id,
                                    'problemId': problem_id},
                                files=files,
                                headers=self._headers_())
            req_json = json.loads(req.text)
            if req.ok:
                result = req_json['result']['value']
                break
            if not req.ok and req_json['error']['message'].startswith("Can't save or update entity"):
                logging.warn("{}. Retrying.".format(req_json['error']['message']))
                time.sleep(1)
                continue
            self._check_request_(req, "Submission error. N_tries:{}".format(n_try))
            break
        if result is None:
            assert False, "Error sending submission"
        self.result_id = result
        return result

    def get_result_async(self, run_id=None):
        assert self.oauth is not None, "Get oauth token first"
        assert run_id is not None or self.result_id is not None, "Result_id is not defined"
        if run_id is None:
            run_id = self.result_id
        url = '{:s}?runId={:d}&contestId={:d}'.format(URL_RESULTS, run_id, self.contest_id)
        req = requests.get(url, headers=self._headers_())
        self._check_request_(req, "Reading result error (RUN:{}, URL:{})".format(run_id, url))
        return json.loads(req.text)

    def get_result(self, run_id=None):
        score = None
        for n_try in xrange(RESULT_TIMEOUT):
            r = self.get_result_async(run_id)
            if len(r['result']['tests']) > 0 and r['result']['tests'][0]['verdict'] == 'ok':
                score = r['result']['submission']['score']['doubleScore']
                break
            logging.info("Submission status: {}".format(r['result']['submission']['status']))
            time.sleep(1)
        return score


class TestStringMethods(unittest.TestCase):

    def setUp(self):
        # go to URL:
        # https://oauth.yandex.ru/authorize?response_type=code&client_id=2ae47301f8e64ae697c122edd7dde763
        # 
        contest = YaContestSubmitter(
            code='6315154',
            oauth_token='21a1929c450641769be5c5bc49a55d54',
            contest_id=CONTEST_ID)
        self.contest = contest

    def test_list_problems(self):
        r = self.contest._list_contest_problems()
        self.assertGreater(len(r), 0)

    def test_submit(self):
        import tempfile
        import textwrap
        with tempfile.NamedTemporaryFile() as fh:
            submission = '''
                2
                1.0 0.0
                1.123456789 9.0987654321
            '''
            fh.write(textwrap.dedent(submission))
            fh.flush()
            r = self.contest.submit(fh.name)
            self.assertGreater(r, 0)

        time.sleep(1)
        score = self.contest.get_result()
        logging.info("score: {}".format(score))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    unittest.main()
