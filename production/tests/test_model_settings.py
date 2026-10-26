import ast,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from flask import Flask,jsonify,request
from CampusPulse import model_connection as mc


class ModelCredentialTests(unittest.TestCase):
    def setUp(self):
        self.saved={'REPORT_ENGINE_BASE_URL':'https://relay.example.invalid/gateway/v1',
                    'REPORT_ENGINE_API_KEY':'stored-dummy-key','REPORT_ENGINE_MODEL_NAME':'old-model'}
        self.load=Mock(return_value=self.saved)
    def test_saved_key_stays_on_exact_engine_endpoint(self):
        key,base,model=mc.resolve_connection({'engine':'REPORT_ENGINE','base_url':'https://relay.example.invalid/gateway/v1/chat/completions','model':'new-model'},self.load)
        self.assertEqual(key,'stored-dummy-key');self.assertEqual(base,self.saved['REPORT_ENGINE_BASE_URL']);self.assertEqual(model,'new-model')
    def test_saved_key_is_not_sent_to_changed_provider_or_path(self):
        for base in ('https://api.deepseek.com/v1','https://relay.example.invalid/other/v1'):
            with self.assertRaisesRegex(ValueError,'接口地址已变更'):
                mc.resolve_connection({'engine':'REPORT_ENGINE','base_url':base},self.load)
    def test_new_key_uses_form_values_without_loading_old_secret(self):
        result=mc.resolve_connection({'engine':'REPORT_ENGINE','base_url':'https://api.deepseek.com/v1','api_key':'new-dummy','model':'selected-model'},self.load)
        self.assertEqual(result,('new-dummy','https://api.deepseek.com/v1','selected-model'));self.load.assert_not_called()
    def test_optional_keyword_optimizer_uses_its_own_saved_key(self):
        self.saved.update(KEYWORD_OPTIMIZER_BASE_URL='https://api.deepseek.com/v1',KEYWORD_OPTIMIZER_API_KEY='optimizer-dummy')
        key,_,_=mc.resolve_connection({'engine':'KEYWORD_OPTIMIZER','base_url':'https://api.deepseek.com/v1','model':'optimizer-model'},self.load)
        self.assertEqual(key,'optimizer-dummy')
    def test_unknown_engine_cannot_read_arbitrary_config(self):
        with self.assertRaises(ValueError):mc.resolve_connection({'engine':'WEB_AUTH','base_url':'https://relay.example.invalid'},self.load)
        self.load.assert_not_called()
    def test_mask_is_not_used_as_a_real_key(self):
        key,_,_=mc.resolve_connection({'engine':'REPORT_ENGINE','base_url':self.saved['REPORT_ENGINE_BASE_URL'],'api_key':'********'},self.load)
        self.assertEqual(key,'stored-dummy-key')
    def test_changed_provider_save_requires_its_own_key(self):
        with self.assertRaisesRegex(ValueError,'接口地址已变更'):
            mc.validate_model_updates({'REPORT_ENGINE_BASE_URL':'https://api.deepseek.com/v1'},self.load)
    def test_save_normalizes_full_chat_url_and_keeps_other_updates(self):
        result=mc.validate_model_updates({'REPORT_ENGINE_BASE_URL':'https://api.deepseek.com/v1/chat/completions','REPORT_ENGINE_API_KEY':'new-dummy','REPORT_ENGINE_MODEL_NAME':'chosen'},self.load)
        self.assertEqual(result['REPORT_ENGINE_BASE_URL'],'https://api.deepseek.com/v1');self.assertEqual(result['REPORT_ENGINE_MODEL_NAME'],'chosen')
    def test_urls_with_embedded_credentials_are_rejected(self):
        for url in ('https://user:pass@example.invalid/v1','https://example.invalid/v1?key=secret','https://example.invalid/v1#secret'):
            with self.assertRaises(ValueError):mc.normalize_base_url(url)


class ModelSettingsRoutes(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.saved={'REPORT_ENGINE_BASE_URL':'https://relay.example.invalid/v1','REPORT_ENGINE_API_KEY':'stored-dummy-key','REPORT_ENGINE_MODEL_NAME':'saved-model'}
        self.write=Mock();self.read=Mock(return_value=self.saved)
        wanted={'fetch_models','test_model_connection','update_config','_is_secret_key','masked_config_values'}
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8'))
        selected=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[])
        scope={'app':self.app,'jsonify':jsonify,'request':request,'read_config_values':self.read,'write_config_values':self.write,'CONFIG_KEYS':list(self.saved),'SECRET_MASK':'********','logger':Mock()}
        exec(compile(selected,'app.py','exec'),scope)
        self.client=self.app.test_client()
    def test_test_route_resolves_stored_key_but_never_returns_it(self):
        with patch.object(mc,'probe',return_value={'success':True,'message':'ok'}) as probe:
            response=self.client.post('/api/test_model',json={'engine':'REPORT_ENGINE','base_url':self.saved['REPORT_ENGINE_BASE_URL'],'model':'unsaved-model'})
        self.assertEqual(response.status_code,200);probe.assert_called_once_with('stored-dummy-key',self.saved['REPORT_ENGINE_BASE_URL'],'unsaved-model')
        self.assertNotIn('stored-dummy-key',response.get_data(as_text=True));self.write.assert_not_called()
    def test_test_route_rejects_changed_provider_before_outbound_call(self):
        with patch.object(mc,'probe') as probe:
            response=self.client.post('/api/test_model',json={'engine':'REPORT_ENGINE','base_url':'https://new.example.invalid/v1','model':'m'})
        self.assertEqual(response.status_code,400);probe.assert_not_called()
    def test_model_list_uses_saved_key_and_handles_model_ids(self):
        response=Mock(status_code=200);response.json.return_value={'data':[{'id':'model-a'},{'id':'model-b'}]}
        with patch('requests.get',return_value=response) as get:
            result=self.client.post('/api/fetch_models',json={'engine':'REPORT_ENGINE','base_url':self.saved['REPORT_ENGINE_BASE_URL']})
        self.assertEqual(result.json['models'],['model-a','model-b']);self.assertEqual(get.call_args.kwargs['headers']['Authorization'],'Bearer stored-dummy-key')
        self.assertNotIn('stored-dummy-key',result.get_data(as_text=True))
    def test_changed_provider_cannot_be_saved_with_old_key(self):
        response=self.client.post('/api/config',json={'REPORT_ENGINE_BASE_URL':'https://new.example.invalid/v1'})
        self.assertEqual(response.status_code,400);self.write.assert_not_called()
    def test_model_only_save_keeps_saved_secret_masked(self):
        with patch('CampusPulse.config.refresh_runtime'):
            response=self.client.post('/api/config',json={'REPORT_ENGINE_MODEL_NAME':'new-model','REPORT_ENGINE_API_KEY':''})
        self.assertEqual(response.status_code,200);self.write.assert_called_once_with({'REPORT_ENGINE_MODEL_NAME':'new-model'})
        self.assertEqual(response.json['config']['REPORT_ENGINE_API_KEY'],'********')
    def test_probe_uses_bounded_output_and_requires_real_response(self):
        client=Mock();client.chat.completions.create._bf_usage_ledger=False
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='OK'))],usage=None)
        with patch('openai.OpenAI',return_value=client),patch.object(mc,'completion',return_value=response) as complete,patch('CampusPulse.telemetry.record_response'):
            result=mc.probe('dummy','https://relay.example.invalid/v1','model')
        self.assertTrue(result['success']);self.assertEqual(complete.call_args.kwargs['max_tokens'],512);client.close.assert_called_once()


if __name__=='__main__':unittest.main()
