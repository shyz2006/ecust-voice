"""Loopback-only validation app, isolated task/runtime/database; never shipped as app entrypoint."""
import os,pathlib,sqlite3,tempfile,json,sys
sys.path.insert(0,'/app')
root=pathlib.Path(tempfile.mkdtemp(prefix='teacher-validation-'))
port=int(os.environ.get('VALIDATION_PORT','15001'))
os.environ.update(BETTAFISH_RUNTIME_DIR=os.environ.get('VALIDATION_RUNTIME_DIR',str(root/'runtime')),SEARCH_GATEWAY_DB=str(root/'search.sqlite3'),
                  LLM_SLOT_DIR=str(root/'llm_slots'),LLM_STATS_FILE=str(root/'llm_stats.json'),
                  PORT=str(port),RESEARCH_PARAGRAPH_CONCURRENCY='1',REPORT_CHAPTER_CONCURRENCY='1',MAX_CONCURRENT_RESEARCH='1')
from CampusPulse.config import settings
source=sqlite3.connect('file:'+str(settings.db_path)+'?mode=ro',uri=True)
target=sqlite3.connect(root/'campus.db');source.backup(target);source.close();target.close()
settings.db_path=root/'campus.db';os.environ['PULSE_DB_PATH']=str(settings.db_path)
from CampusPulse import storage
with storage.connect():pass
from CampusPulse import revision
from CampusPulse.blueprint import pulse_bp
from ReportEngine.flask_interface import report_bp,initialize_report_engine
if os.environ.get('VALIDATION_RUNTIME_DIR'):initialize_report_engine()
from flask import Flask,session,send_file,jsonify
app=Flask('teacher-candidate',static_folder='/app/static');app.secret_key='candidate-validation-only'
app.register_blueprint(pulse_bp,url_prefix='/pulse');app.register_blueprint(report_bp,url_prefix='/api/report')
@app.route('/')
def home():return send_file('/app/templates/index.html')
@app.route('/validation/login')
def login():session['authenticated']=True;session['username']='isolated-validator';return jsonify(success=True)
@app.route('/validation/health')
def health():return jsonify(success=True,isolated=True)
@app.route('/api/config')
def config():return jsonify(success=True,config={})
from utils.research_runner import start_reaper
start_reaper(5)
app.run(host='127.0.0.1',port=port,threaded=True,use_reloader=False)
