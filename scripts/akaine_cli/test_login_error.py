"""Fixed native login-error allowlist and stale-submit regression checks."""
import copy
import unittest
import akaine_stag as cli
from test_akaine_stag import FakeAdb

class LoginErrorTests(unittest.TestCase):
    def account(self,code=None):
        return {'kind':'login','signed_in':False,'blocked':False,'can_open':False,'can_login_open':False,
            'can_fill':True,'can_submit':True,'can_accept_terms':False,'error_code':code,
            'error_text':cli.ACCOUNT_ERRORS.get(code)}

    def test_all_canonical_errors_and_legacy_status(self):
        for code in [None,*cli.ACCOUNT_ERRORS]:
            cli.validate_domain_response({'account':self.account(code)},'account','status')
        legacy=self.account();del legacy['error_code'];del legacy['error_text']
        cli.validate_domain_response({'account':legacy},'account','status')

    def test_unknown_or_raw_error_text_rejected(self):
        valid=self.account('connection_failed')
        for field,value in [('error_code','raw_server_error'),('error_code',[]),('error_code',{}),
                ('error_text','PRIVATE_BANNER_SENTINEL'),('error_text',34),('kind','logged_in_menu')]:
            other={**valid,field:value}
            with self.subTest(field=field,value=value),self.assertRaises(cli.CliError):
                cli.validate_domain_response({'account':other},'account','status')
        for missing in ('error_code','error_text'):
            other=copy.deepcopy(valid);del other[missing]
            with self.assertRaises(cli.CliError):cli.validate_domain_response({'account':other},'account','status')

    def test_failed_submit_is_known_failure_and_never_retried(self):
        device=FakeAdb();device.response_override={'ok':False,'error':{'code':'ACCOUNT_LOGIN_FAILED','message':'Native fixed inline failure.'},
            'state':{'account':self.account('invalid_credentials')}}
        result=device.client().execute('account','submit')
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'ACCOUNT_LOGIN_FAILED')
        self.assertIs(result['error']['outcome_unknown'],False);self.assertIs(result['error']['automatic_retry'],False)
        self.assertEqual(len(device.requests),1)

    def test_unrecognized_old_or_missing_label_cannot_claim_fast_failure(self):
        for code in (None,'unrecognized'):
            device=FakeAdb();device.response_override={'ok':False,'error':{'code':'ACCOUNT_LOGIN_FAILED','message':'failure'},
                'state':{'account':self.account(code)}}
            result=device.client().execute('account','submit')
            self.assertEqual(result['error']['code'],'PROTOCOL_ERROR');self.assertEqual(len(device.requests),1)

    def test_failure_wrong_command_or_contradictory_state_rejected(self):
        for command,argument,changes in [('account','status',{}),('account','submit',{'blocked':True}),
                ('account','submit',{'signed_in':True}),('account','submit',{'can_submit':False})]:
            device=FakeAdb();device.response_override={'ok':False,'error':{'code':'ACCOUNT_LOGIN_FAILED','message':'failure'},
                'state':{'account':{**self.account('connection_failed'),**changes}}}
            result=device.client().execute(command,argument)
            self.assertEqual(result['error']['code'],'PROTOCOL_ERROR')

if __name__ == "__main__": unittest.main()
