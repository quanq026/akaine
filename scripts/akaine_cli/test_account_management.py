"""Exact account management/logout union with current inline login-error guards."""
import contextlib
import copy
import io
import unittest
from unittest.mock import patch

import akaine_stag as cli
from test_akaine_stag import FakeAdb


class AccountManagementTests(unittest.TestCase):
    def account(self, kind='logged_in_menu', **changes):
        value={'kind':kind,'signed_in':True,'blocked':False,'can_open':False,'can_login_open':False,
               'can_fill':False,'can_submit':False,'can_accept_terms':False,
               'can_management_open':kind=='logged_in_menu','can_logout':kind=='account_management',
               'error_code':None,'error_text':None}
        value.update(changes)
        return value

    def validate(self, value, argument='status'):
        cli.validate_domain_response({'account':value},'account',argument)

    def test_exact_management_and_logout_states(self):
        self.validate(self.account())
        self.validate(self.account('account_management'),'management_open')
        self.validate(self.account('main_menu',signed_in=False,can_open=True),'logout')
        blocked=self.account('account_management',blocked=True,can_logout=False)
        self.validate(blocked)
        for value,arg in ((self.account(),'management_open'),(self.account('account_management'),'logout')):
            with self.assertRaises(cli.CliError):self.validate(value,arg)

    def test_capability_shape_and_signed_in_ownership(self):
        good=self.account('account_management')
        for changes in ({'signed_in':False},{'blocked':True},{'can_open':True},{'can_fill':True},
                        {'can_accept_terms':True},{'can_management_open':True},{'can_logout':1}):
            with self.subTest(changes=changes),self.assertRaises(cli.CliError):self.validate({**good,**changes})
        for key in ('can_management_open','can_logout'):
            bad=copy.deepcopy(good);del bad[key]
            with self.assertRaises(cli.CliError):self.validate(bad)
        legacy=self.account('main_menu',signed_in=False,can_open=True)
        del legacy['can_management_open'];del legacy['can_logout']
        self.validate(legacy)
        with self.assertRaises(cli.CliError):self.validate(legacy,'logout')

    def test_terms_and_inline_errors_stay_separate(self):
        self.validate(self.account('login_terms_required',signed_in=False,blocked=True,can_accept_terms=True))
        with self.assertRaises(cli.CliError):self.validate(self.account('login_terms_required',signed_in=False,
            blocked=True,can_accept_terms=True,can_logout=True))
        value=self.account('login',signed_in=False,can_fill=True,can_submit=True,
                           error_code='invalid_credentials',error_text=cli.ACCOUNT_ERRORS['invalid_credentials'])
        self.validate(value)
        value['kind']='account_management';value['can_fill']=value['can_submit']=False;value['can_logout']=True
        with self.assertRaises(cli.CliError):self.validate(value)

    def test_parser_mutation_and_no_destructive_argument(self):
        for argument in ('management_open','logout'):
            self.assertTrue(cli.domain_argument('account',argument))
            self.assertTrue(cli.mutation('account',argument))
        for argument in ('delete','delete_account','reset','upload'):
            self.assertFalse(cli.domain_argument('account',argument))
        for operation,wire in (('management-open','management_open'),('logout','logout')):
            with patch.object(cli,'Client')as client,contextlib.redirect_stdout(io.StringIO()):
                client.return_value.execute.return_value={'ok':True}
                self.assertEqual(cli.main(['--serial','emulator-5556','account',operation]),0)
                self.assertEqual(client.return_value.execute.call_args.args[:2],('account',wire))

    def test_logout_confirmation_is_native_signed_out_and_never_retried(self):
        device=FakeAdb();device.response_override={'ok':True,'state':{'screen':'main_menu',
            'account':self.account('main_menu',signed_in=False,can_open=True)}}
        result=device.client().execute('account','logout')
        self.assertTrue(result['ok']);self.assertEqual(len(device.requests),1)
        device=FakeAdb();device.respond=False
        result=device.client(1).execute('account','logout')
        self.assertFalse(result['ok']);self.assertEqual(len(device.requests),1)
        self.assertIs(result['error']['outcome_unknown'],True)
        self.assertIs(result['error']['automatic_retry'],False)


if __name__=='__main__':unittest.main()
