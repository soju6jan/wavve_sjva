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

# 패키지
from .plugin import package_name, logger
from .model import ModelSetting, ModelWavveEpisode
import framework.wavve.api as Wavve

import ffmpeg

#########################################################
        
class LogicBasic(object):
    @staticmethod
    def login(force=False):
        try:
            if ModelSetting.get('credential') == '' or  force:
                credential = Wavve.do_login(ModelSetting.get('id'), ModelSetting.get('pw'))
                logger.info('Wavve Credential : %s', credential)
                if credential is None:
                    return False
                ModelSetting.set('credential', credential)
                db.session.commit()
            else:
                pass
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def analyze(url, quality=None):
        try:
            logger.debug('analyze :%s', url)
            url_type = None
            code = None
            corner_id = None
            vod_type = None
            if url.startswith('http'):
                match = re.compile(r'contentid\=(?P<contentid>.*?)(\&|$|\#)').search(url)
                match2 = re.compile(r'programid\=(?P<programid>.*?)(\&|$|\#)').search(url)
                if match:
                    code = match.group('contentid')
                    url_type = 'episode'
                elif match2:
                    url_type = 'program'
                    code = match2.group('programid')
                else:
                    match = re.compile(r'movieid\=(?P<movieid>.*?)($|\#)').search(url)
                    if match:
                        url_type = 'movie'
                        code = match.group('movieid')
            else:
                if len(url.split('.')) == 2:
                    url_type = 'episode'
                    code = url.strip()
                elif url.startswith('MV_'):
                    url_type = 'movie'
                    code = url.strip()
                elif url.find('_') != -1:
                    url_type = 'program'
                    code = url.strip()
                else:
                    pass
            logger.debug('Analyze %s %s', url_type, code)
            if url_type is None:
                return {'url_type':'None'}
            elif url_type == 'episode':
                if quality is None:
                    quality = ModelSetting.get('quality')
                data = Wavve.vod_contents_contentid(code)
                contenttype = 'onairvod' if data['type'] == 'onair' else 'vod'
                proxy = None
                data2 = Wavve.streaming(contenttype, code, quality, ModelSetting.get('credential'))
                try:
                    tmp = data2['playurl']
                except:
                    try:
                        LogicBasic.login()
                        data2 = Wavve.streaming(contenttype, code, quality, ModelSetting.get('credential'))
                    except:
                        pass

                #logger.debug(data2)
                data3 = {}
                data3['filename'] = Wavve.get_filename(data, quality)
                data3['preview'] = (data2['playurl'].find('preview') != -1)
                data3['current_quality'] = quality
                ModelSetting.set('recent_code', code)
                return {'url_type': url_type, 'code':code, 'episode' : data, 'streaming':data2, 'available' : data3}
            elif url_type == 'program':
                data = Wavve.vod_program_contents_programid(code)
                ModelSetting.set('recent_code', code)
                return {'url_type': url_type, 'page':'1', 'code':code, 'data' : data}
            elif url_type == 'movie':
                if quality is None:
                    quality = ModelSetting.get('quality')
                data = Wavve.movie_contents_movieid(code)
                data2 = Wavve.streaming('movie', code, quality, ModelSetting.get('credential'))
                try:
                    tmp = data2['playurl']
                except:
                    try:
                        LogicBasic.login()
                        data2 = Wavve.streaming('movie', code, quality, ModelSetting.get('credential'))
                    except:
                        pass

                data3 = {}
                data3['filename'] = Wavve.get_filename(data, quality)
                data3['preview'] = (data2['playurl'].find('preview') != -1)
                data3['current_quality'] = quality
                ModelSetting.set('recent_code', code)
                return {'url_type': url_type, 'code':code, 'info' : data, 'streaming':data2, 'available':data3}
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())        

    
    @staticmethod
    def analyze_program_page(code, page):
        try:
            data = Wavve.vod_program_contents_programid(code, page=page)
            return {'url_type': 'program', 'page':page, 'code':code, 'data' : data}
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())  


    @staticmethod
    def download_url(url, filename):
        try:
            logger.debug('download_url : %s', url)
            save_path = ModelSetting.get('save_path')
            max_pf_count = ModelSetting.get('max_pf_count')
            tmp = Wavve.get_prefer_url(url)
            proxy = None
            if ModelSetting.get_bool('use_proxy'):
                proxy = ModelSetting.get('proxy_url')
            f = ffmpeg.Ffmpeg(tmp, filename, plugin_id=-1, listener=LogicBasic.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='wavve_basic', save_path=save_path, proxy=proxy)
            #f.start_and_wait()
            f.start()
            #time.sleep(60)
            return True

        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc()) 


    @staticmethod
    def ffmpeg_listener(**arg):
        import ffmpeg
        refresh_type = None
        if arg['type'] == 'status_change':
            if arg['status'] == ffmpeg.Status.DOWNLOADING:
                episode = db.session.query(ModelWavveEpisode).filter_by(id=arg['plugin_id']).with_for_update().first()
                if episode:
                    episode.ffmpeg_status = int(arg['status'])
                    episode.duration = arg['data']['duration']
                    db.session.commit()
            elif arg['status'] == ffmpeg.Status.COMPLETED:
                pass
            elif arg['status'] == ffmpeg.Status.READY:
                pass
        elif arg['type'] == 'last':
            episode = db.session.query(ModelWavveEpisode).filter_by(id=arg['plugin_id']).with_for_update().first()
            if episode:
                episode.ffmpeg_status = int(arg['status'])
                if arg['status'] == ffmpeg.Status.WRONG_URL or arg['status'] == ffmpeg.Status.WRONG_DIRECTORY or arg['status'] == ffmpeg.Status.ERROR or arg['status'] == ffmpeg.Status.EXCEPTION:
                    episode.etc_abort = 1
                elif arg['status'] == ffmpeg.Status.USER_STOP:
                    episode.user_abort = True
                    logger.debug('Status.USER_STOP received..')
                elif arg['status'] == ffmpeg.Status.COMPLETED:
                    episode.completed = True
                    episode.end_time = datetime.now()
                    episode.download_time = (episode.end_time - episode.start_time).seconds
                    episode.filesize = arg['data']['filesize']
                    episode.filesize_str = arg['data']['filesize_str']
                    episode.download_speed = arg['data']['download_speed']
                    logger.debug('Status.COMPLETED received..')
                elif arg['status'] == ffmpeg.Status.TIME_OVER:
                    episode.etc_abort = 2
                elif arg['status'] == ffmpeg.Status.PF_STOP:
                    episode.pf = int(arg['data']['current_pf_count'])
                    episode.pf_abort = 1
                elif arg['status'] == ffmpeg.Status.FORCE_STOP:
                    episode.etc_abort = 3
                elif arg['status'] == ffmpeg.Status.HTTP_FORBIDDEN:
                    episode.etc_abort = 4
                db.session.commit()
                logger.debug('LAST commit %s', arg['status'])
                from .logic_recent import LogicRecent
                LogicRecent.current_auto_count_ffmpeg -= 1
        elif arg['type'] == 'log':
            pass
        elif arg['type'] == 'normal':
            pass
        if refresh_type is not None:
            pass
