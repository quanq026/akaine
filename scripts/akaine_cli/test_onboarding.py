"""Exact first-run onboarding and Main Menu guide contracts; no ADB or native execution."""
import copy
import unittest
import akaine_stag as cli

class OnboardingContract(unittest.TestCase):
    def state(self, stage='welcome', action='onboarding_setup'):
        return {'screen':'main_menu','ui':{'context':'a'*16,'modal_present':True,'reason':None,
            'onboarding_stage':stage,'actions':[{'token':action+'.'+'a'*16,'name':cli.UI_LABELS[action],'enabled':True}],
            'overlays':[],'overlay_scan_complete':True,'overlay_coverage':list(cli.OVERLAY_COVERAGE)}}

    def test_notification_hint_exact_contract(self):
        state=self.state(); ui=state['ui']; ui['modal_present']=False; ui['onboarding_stage']=None
        ui['reason']='input_blocked'; ui['actions']=[{'token':'notification_hint_continue.'+'a'*16,'name':cli.UI_LABELS['notification_hint_continue'],'enabled':True}]
        ui['overlays']=[{'kind':'tutorial','id':'notification_permission_guide','active':True,'visible':True,'opacity':255,'blocks_input':True}]
        self.assertEqual(cli.validate_ui(state)['actions'][0]['token'],'notification_hint_continue.'+'a'*16)
        for key,value in [('id','unknown_progression_guide'),('active',False)]:
            other=copy.deepcopy(state); other['ui']['overlays'][0][key]=value
            with self.assertRaises(cli.CliError):cli.validate_ui(other)
        other=copy.deepcopy(state); other['screen']='song_select'
        with self.assertRaises(cli.CliError):cli.validate_ui(other)
        other=copy.deepcopy(state); other['ui']['actions'][0]={'token':'main_music.'+'a'*16,'name':'Music','enabled':True}
        with self.assertRaises(cli.CliError):cli.validate_ui(other)

    def test_main_menu_hint_exact_contract(self):
        state=self.state(); ui=state['ui']; ui['modal_present']=False; ui['onboarding_stage']=None
        ui['reason']='input_blocked'; ui['actions']=[{'token':'main_hint_continue.'+'a'*16,'name':'Continue main menu guide','enabled':True}]
        ui['overlays']=[{'kind':'tutorial','id':'main_menu_hint','active':True,'visible':True,'opacity':255,'blocks_input':True}]
        self.assertEqual(cli.validate_ui(state)['actions'][0]['name'],'Continue main menu guide')
        for path,value in [('id','unknown_progression_guide'),('active',False)]:
            other=copy.deepcopy(state); other['ui']['overlays'][0][path]=value
            with self.assertRaises(cli.CliError):cli.validate_ui(other)
        other=copy.deepcopy(state); other['screen']='song_select'
        with self.assertRaises(cli.CliError):cli.validate_ui(other)
        other=copy.deepcopy(state); other['ui']['actions'][0]={'token':'main_music.'+'a'*16,'name':'Music','enabled':True}
        with self.assertRaises(cli.CliError):cli.validate_ui(other)

    def test_three_exact_modal_stages(self):
        for stage,action in [('welcome','onboarding_setup'),('offset_setup','onboarding_cancel'),
                ('offset_skip_confirmation','onboarding_skip')]:
            self.assertEqual(cli.validate_ui(self.state(stage,action))['actions'][0]['token'], action+'.'+'a'*16)

    def test_unknown_or_mismatched_stage_cannot_release_modal(self):
        for value in (None, False, 1, [], {}, 'unknown', 'offset_setup'):
            with self.subTest(stage=value), self.assertRaises(cli.CliError): cli.validate_ui(self.state(value))

    def test_modal_contract_stays_narrow(self):
        state=self.state()
        variants=[]
        for path,value in [('screen','song_select'),('modal_present',False),('reason','loading'),
                ('overlay_scan_complete',False),('name','Music'),('token','main_music.'+'a'*16)]:
            other=copy.deepcopy(state)
            if path=='screen': other[path]=value
            elif path in ('name','token'): other['ui']['actions'][0][path]=value
            else: other['ui'][path]=value
            variants.append(other)
        other=copy.deepcopy(state); other['ui']['actions'].append({'token':'main_music.'+'a'*16,'name':'Music','enabled':True}); variants.append(other)
        for other in variants:
            with self.subTest(state=other), self.assertRaises(cli.CliError): cli.validate_ui(other)

if __name__ == "__main__": unittest.main()
