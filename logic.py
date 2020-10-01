# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
import re
import urllib
from datetime import datetime

# third-party
from pytz import timezone
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify

# sjva 공용
from framework import app, db, scheduler, path_data
from framework.logger import get_logger
from framework.job import Job
from framework.util import Util
import framework.wavve.api as Wavve

# 패키지
from plugin import logger, package_name
import ffmpeg
from .model import ModelSetting
from .logic_basic import LogicBasic
from .logic_recent import LogicRecent
### edit by lapis
from .logic_program import LogicProgram
###

#########################################################
        
class Logic(object):
    db_default = { 
        # 기본
        'id' : '', 
        'pw' : '', 
        'credential' : '',
        'quality' : '1080p',
        'save_path' : os.path.join(path_data, 'download'),
        'max_pf_count' : '0',
        'max_retry_count' : '0',
        'recent_code' : '',
        'use_proxy' : 'False',
        'proxy_url' : '',
        
        # 최근
        'auto_interval' : '5', 
        'auto_start' : 'False', 
        'auto_quality' : '1080p',        
        'retry_user_abort' : 'False',
        'qvod_download' : 'False',
        'except_channel' : '',
        'except_program' : '',
        'auto_page' : '2',
        'auto_save_path' : os.path.join(path_data, 'download'),
        'download_program_in_qvod' : '',
        'download_mode' : '0',
        'whitelist_program' : '',
        'whitelist_first_episode_download' : 'True',
        'auto_count_ffmpeg' : '4',
        '2160_receive_1080' : 'False',
        '2160_wait_minute' : '100',

        # 방송별
        'program_auto_path' : os.path.join(path_data, 'download'),
        'program_auto_make_folder' : 'True', 
        'program_auto_count_ffmpeg' : '4',
        'program_auto_quality' : '1080p', 
        'program_auto_download_failed': 'True', # edit by lapis

        'qvod_check_quality' : 'False'
        
    }
    

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            logger.debug('%s plugin_load', package_name)
            # DB 초기화
            Logic.db_init()
            LogicBasic.login()

            if ModelSetting.get('auto_start') == 'True':
                Logic.scheduler_start()
            
            ### edit by lapis
            if ModelSetting.get('program_auto_download_failed') == 'True':
                LogicProgram.retry_download_failed()
            ###

            # 편의를 위해 json 파일 생성
            from plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_start():
        try:
            interval = ModelSetting.get('auto_interval')
            job = Job(package_name, package_name, interval, Logic.scheduler_function, u"웨이브 최신 TV VOD 다운로드", True)
            scheduler.add_job_instance(job)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_stop():
        try:
            scheduler.remove_job(package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def setting_save(req):
        try:
            flag_login = False
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                if key == 'id' or key == 'pw':
                    if entity.value != value:
                        flag_login = True
                if entity is not None:
                    entity.value = value
            db.session.commit()                    
            if flag_login:
                if LogicBasic.login(force=True):
                    return 1
                else: 
                    return 2
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.error('key:%s value:%s', key, value)
            return False


    @staticmethod
    def scheduler_function():
        try:
            LogicRecent.scheduler_function()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    # 기본 구조 End
    ##################################################################

