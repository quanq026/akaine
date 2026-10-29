"""Typed native Note Speed confirmation contract; no ADB or native execution."""
import contextlib
import io
import unittest
from unittest.mock import patch
import akaine_stag as cli

class SpeedCommandTests(unittest.TestCase):
    def ui(self):
        return {'context':'a'*16,'modal_present':False,'reason':None,'actions':[],
            'overlays':[],'overlay_scan_complete':True,'overlay_coverage':list(cli.OVERLAY_COVERAGE)}

    def state(self):
        return {'screen':'song_select','gameplay':False,'ui':self.ui(),
            'song_selection':{'song_id':'testify','difficulty':2}}

    def test_command_accepts_only_expected_song_identifiers(self):
        self.assertTrue(cli.domain_argument('play_set_speed','testify'))
        for name in ('','x y','../testify','song;bad','x'*65):
            self.assertFalse(cli.domain_argument('play_set_speed',name))

    def test_confirmation_requires_native_setup_gone_and_same_song(self):
        cli.validate_domain_response(self.state(),'play_set_speed','testify')
        state=self.state(); state['song_selection']['song_id']='other'
        with self.assertRaises(cli.CliError):cli.validate_domain_response(state,'play_set_speed','testify')
        state=self.state(); state['ui']['overlays']=[{'kind':'tutorial','id':'note_speed_setup','active':True,'visible':True,'opacity':255,'blocks_input':True}]
        with self.assertRaises(cli.CliError):cli.validate_domain_response(state,'play_set_speed','testify')
        state=self.state(); state['ui']['overlay_scan_complete']=False
        with self.assertRaises(cli.CliError):cli.validate_domain_response(state,'play_set_speed','testify')

    def test_setup_blocks_underlying_music_actions(self):
        state=self.state(); state['ui']['overlays']=[{'kind':'tutorial','id':'note_speed_setup','active':True,'visible':True,'opacity':255,'blocks_input':True}]
        cli.validate_ui(state)
        state['ui']['actions']=[{'token':'main_music.'+'a'*16,'name':'Music','enabled':True}]
        with self.assertRaises(cli.CliError):cli.validate_ui(state)

    def test_cli_maps_confirm_speed_to_typed_command_without_value(self):
        with patch.object(cli,'Client') as client,contextlib.redirect_stdout(io.StringIO()):
            client.return_value.execute.return_value={'ok':True}
            self.assertEqual(cli.main(['--serial','emulator-5556','song','confirm-speed','testify']),0)
            client.return_value.execute.assert_called_once_with('play_set_speed','testify',None,{'id':'testify'},None)

if __name__ == "__main__": unittest.main()
