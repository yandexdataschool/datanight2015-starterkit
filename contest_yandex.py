#!/usr/bin/env python

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
SCORE_TIMEOUT = 30
APPLICATION_ID = '2ae47301f8e64ae697c122edd7dde763'
CLIENT_SECRET = 'a4d1256f2c3d4ddfa5fa83ec60862e59'
RETRY_PAUSE = 1


def code2oauth_token(code):
    """
    Return ntuple (status, message, oauth) for given code.
    Oauth is long-lived token from temporary code to authenticate user for 
    given application

    code -- code 7-digit number you get from 
        https://oauth.yandex.ru/authorize?response_type=code&client_id=2ae47301f8e64ae697c122edd7dde763
    """
    oauth = None
    r = requests.post(
        URL_TOKEN,
        data={
            'grant_type': 'authorization_code',
            'client_id': APPLICATION_ID,
            'client_secret': CLIENT_SECRET,
            'code': code
        })

    if not r.ok:
        message = "{} ({})".format(
            r.json()['error'],
            r.json()['error_description'])
        logging.error(message)
    else:
        oauth = r.json()['access_token']
        message = "Success"
        logging.debug("OAuth token: {}".format(oauth))
    return r.ok, message, oauth


class YaContestSubmitter(object):
    def __init__(self, contest_id, code=None, oauth_token=None):
        """
        creates Yandex Contest wrapper for submitting solutions & getting scores

        Arguments:
        contest_id -- ID of contest you want to submit
        code -- temporary code that would be converted to oauth_token, used only oauth_token is None
        oauth_token -- oauth token

        if constructor fails to convert code to oauth token or no oauth token is given, it raises Exception
        """
        self.oauth = oauth_token
        self.contest_id = contest_id
        if oauth_token is None and code is not None:
            status, message, oauth = code2oauth_token(code)
            if status:
                self.oauth = oauth
        if self.oauth is None:
            raise Exception("Cannot obtain oauth token")

    def _list_contest_problems(self, contest_id=None):
        assert self.contest_id is not None or contest_id is not None
        if contest_id is None:
            contest_id = self.contest_id
        r = requests.get(
            URL_PROBLEMS,
            params={'contestId': contest_id,
                    'locale': 'ru'})
        self._check_request(r, "Get list of problems error")
        return r.json()

    def _get_first_contest_problem(self):
        r = self._list_contest_problems()
        return r['result']['problems'][0]

    def _headers(self):
        return {'Authorization': 'OAuth {}'.format(self.oauth)}

    def _check_request(self, req, error_message):
        if not req.ok:
            raise Exception("{}: {} ({})".format(
                error_message, 
                req.json()['error']['message'],
                req.text))

    def submit(self, filename):
        """
        Submits file to Ya.Contest and returns submission Id that could be used for getting submission score

        filename -- submission file
        """
        assert self.oauth is not None, "Get oauth token first"
        files = {'file': open(filename, 'rb')}
        problem_id = self._get_first_contest_problem()['id']
        result = None
        for n_try in xrange(MAX_RETRIES):
            req = requests.post(URL_SUBMIT,
                                data={
                                    'contestId': self.contest_id,
                                    'problemId': problem_id},
                                files=files,
                                headers=self._headers())
            req_json = req.json()
            if req.ok:
                result = req_json['result']['value']
                break
            elif req_json['error']['message'].startswith("Can't save or update entity"):
                logging.warn("{}. Retrying.".format(req_json['error']['message']))
                time.sleep(RETRY_PAUSE)
                continue
            self._check_request(req, "Submission error. N_tries:{}".format(n_try))
            break
        if result is None:
            raise Exception("Error sending submission")
        self.result_id = result
        return result

    def get_score_async(self, run_id=None):
        assert self.oauth is not None, "Get oauth token first"
        assert run_id is not None or self.result_id is not None, "Result_id is not defined"
        if run_id is None:
            run_id = self.result_id
        req = requests.get(
            URL_RESULTS,
            params={
                'runId': run_id,
                'contestId': self.contest_id
            },
            headers=self._headers())
        self._check_request(req, "Reading result error (RUN:{})".format(run_id))
        return req.json()

    def get_score(self, run_id=None):
        """
        Returns previous submission score and message from Ya.Contest 

        run_id -- number returned by previous 'submit'
        It waits SCORE_TIMEOUT seconds before giving up.
        """
        score = None
        message = None
        for n_try in xrange(SCORE_TIMEOUT):
            r = self.get_score_async(run_id)
            if len(r['result']['tests']) > 0 and r['result']['tests'][0]['verdict'] == 'ok':
                assert 'score' in r['result']['submission'], "invalid contest response: {}".format(r)
                score = r['result']['submission']['score']['doubleScore']
                message = r['result']['tests'][0]['message']
                break
            logging.info("Submission status: {}".format(r['result']['submission']['status']))
            time.sleep(RETRY_PAUSE)
        return score, message


class TestStringMethods(unittest.TestCase):

    def setUp(self):
        contest = YaContestSubmitter(
            code='6315154',
            oauth_token='21a1929c450641769be5c5bc49a55d54',
            contest_id=CONTEST_ID)
        self.contest = contest

    def test_no_oauth(self):
        with self.assertRaises(Exception):
            c = YaContestSubmitter(CONTEST_ID)
            self.assertEquals(c.contest_id, CONTEST_ID)

    def test_code2oauth(self):
        status, message, oauth = code2oauth_token('6315154')
        self.assertFalse(status)

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
        score, message = self.contest.get_score()
        logging.info("score: {}, message: {}".format(score, message))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    unittest.main()
