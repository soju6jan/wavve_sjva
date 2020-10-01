# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import logging
import json

# third-party
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from flask_socketio import SocketIO, emit, send

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, socketio
from framework.util import Util, AlchemyEncoder

# 로그
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

# 패키지
import framework.wavve.api as Wavve
from .model import ModelSetting, ModelWavveProgram
from .logic import Logic
from .logic_recent import LogicRecent
from .logic_program import LogicProgram, WavveProgramEntity


blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

def plugin_load():
    Logic.plugin_load()

def plugin_unload():
    Logic.plugin_unload()

plugin_info = {
    'version' : '0.1.0.0',
    'name' : '웨이브 다운로드',
    'category_name' : 'vod',
    'icon' : '',
    'developer' : 'soju6jan',
    'description' : '웨이브에서 VOD 다운로드',
    'home' : 'https://github.com/soju6jan/wavve',
    'more' : '',
}
#########################################################

menu = {
    'main' : [package_name, '웨이브'],
    'sub' : [
        ['basic', '기본'], ['recent', '최근방송 자동'], ['program', '프로그램별 자동'], ['log', '로그']
    ]
}   


#########################################################
# WEB Menu                                    
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/recent' % package_name)


@blueprint.route('/<sub>')
@login_required
def first_menu(sub):
    if sub == 'basic':
        try:
            return redirect('/%s/%s/setting' % (package_name, sub))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'recent':
        try:
            return redirect('/%s/%s/list' % (package_name, sub))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'program':
        try:
            return redirect('/%s/%s/select' % (package_name, sub))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


@blueprint.route('/<sub>/<sub2>')
@login_required
def second_menu(sub, sub2):
    if sub == 'basic':
        if sub2 == 'setting':
            try:
                arg = ModelSetting.to_dict()
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'download':
            try:
                arg = {}
                arg["code"] = request.args.get('code')
                if arg['code'] is None:
                    arg['code'] = ModelSetting.get('recent_code')
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
    elif sub == 'recent':
        if sub2 == 'setting':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                arg['scheduler'] = str(scheduler.is_include(package_name))
                arg['is_running'] = str(scheduler.is_running(package_name))
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'list':
            try:
                arg = {}
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
    elif sub == 'program':
        if sub2 == 'setting':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'queue':
            try:
                arg = {}
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'list':
            try:
                arg = {}
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'select':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                arg["code"] = request.args.get('code')
                if arg['code'] is None:
                    arg["code"] = ModelSetting.get('recent_code')
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))



#########################################################
# For UI                                                            
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    logger.debug('Wavve AJAX sub:%s', sub)
    try:     
        if sub == 'setting_save':
            try:
                ret = Logic.setting_save(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')
        elif sub == 'scheduler':
            try:
                go = request.form['scheduler']
                logger.debug('scheduler :%s', go)
                if go == 'true':
                    Logic.scheduler_start()
                else:
                    Logic.scheduler_stop()
                return jsonify(go)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')
        #elif sub == 'wavve_credential_reset':
        #    #ModelSetting.set('credential', '')
        #    from .logic_basic import LogicBasic
        #    LogicBasic.login(force=True)
        #    return jsonify(True)
        #elif sub == 'login':
        #    try:
        #        ret = Wavve.do_login(request.form['id'], request.form['pw'], json_return=True)
        #        return jsonify(ret)
        #    except Exception as e: 
        #        logger.error('Exception:%s', e)
        #        logger.error(traceback.format_exc())
        #        return jsonify('fail')
        
        #########################################################
        # 기본
        #########################################################
        # 프로그램에서도 사용
        elif sub == 'analyze':
            url = request.form['url']
            quality = None
            if 'quality' in request.form:
                quality = request.form['quality']
            from .logic_basic import LogicBasic
            ret = LogicBasic.analyze(url, quality=quality)
            return jsonify(ret)
        elif sub == 'episode_download_url':
            logger.debug(request.form)
            url = request.form['url']
            filename = request.form['filename']
            logger.debug('download %s %s', url, filename)
            from .logic_basic import LogicBasic
            ret = LogicBasic.download_url(url, filename)
            return jsonify(ret)
       

        #########################################################
        # 자동
        #########################################################
        elif sub == 'auto_list':
            try:
                ret = LogicRecent.get_list(request)
                logger.debug('len list :%s', len(ret))
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
        elif sub == 'add_condition_list':
            try:
                ret = LogicRecent.add_condition_list(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub == 'reset_db':
            try:
                ret = LogicRecent.reset_db()
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())  


        #########################################################
        # 프로그램
        #########################################################
        # more버튼
        elif sub == 'program_page':
            try:
                code = request.form['code']
                page = request.form['page']
                from .logic_basic import LogicBasic
                ret = LogicBasic.analyze_program_page(code, page)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())  
        # 화질확인
        elif sub == 'get_contents':
            try:
                code = request.form['code']
                ret = Wavve.vod_contents_contentid(code)
                ret = Wavve.streaming(ret['type'], ret['contentid'], '2160p', ModelSetting.get('credential'))
                try:
                    tmp = ret['playurl']
                except:
                    try:
                        from .logic_basic import LogicBasic
                        LogicBasic.login()
                        ret = Wavve.streaming(ret['type'], ret['contentid'], '2160p', ModelSetting.get('credential'))
                    except:
                        pass

                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())  
        elif sub == 'download_program':
            try:
                ret = LogicProgram.download_program(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())  
        elif sub == 'download_program_check':
            try:
                ret = LogicProgram.download_program_check(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub == 'program_auto_command':
            try:
                ret = LogicProgram.program_auto_command(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        ### edit by lapis
        elif sub == 'program_list_command':
            try:
                ret = LogicProgram.program_list_command(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        ###
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())

# 2020-02-18 by Starbuck
#@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
#def api(sub):
#    if sub == 'chunklist.m3u8':


### program queue
sid_list = []
@socketio.on('connect', namespace='/%s' % package_name)
def connect():
    try:
        logger.debug('socket_connect')
        sid_list.append(request.sid)
        tmp = None
        
        #if Logic.current_data is not None:
        data = [_.__dict__ for _ in WavveProgramEntity.entity_list]
        tmp = json.dumps(data, cls=AlchemyEncoder)
        tmp = json.loads(tmp)
        emit('on_connect', tmp, namespace='/%s' % package_name)
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


@socketio.on('disconnect', namespace='/%s' % package_name)
def disconnect():
    try:
        sid_list.remove(request.sid)
        logger.debug('socket_disconnect')
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


def socketio_callback(cmd, data):
    if sid_list:
        tmp = json.dumps(data, cls=AlchemyEncoder)
        tmp = json.loads(tmp)
        socketio.emit(cmd, tmp , namespace='/%s' % package_name, broadcast=True)

def socketio_list_refresh():
    data = [_.__dict__ for _ in WavveProgramEntity.entity_list]
    tmp = json.dumps(data, cls=AlchemyEncoder)
    tmp = json.loads(tmp)
    socketio_callback('list_refresh', tmp)