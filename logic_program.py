# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
from datetime import datetime
import time
import Queue
import threading
# third-party
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify
from sqlalchemy import desc, or_

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data
from framework.job import Job
from framework.util import Util

# 패키지
import plugin
from .plugin import package_name, logger
from .model import ModelSetting, ModelWavveProgram
import framework.wavve.api as Wavve

#########################################################


class WavveProgramEntity(object):

    current_entity_id = 1
    entity_list = []

    def __init__(self, episode_code, quality):
        self.entity_id = WavveProgramEntity.current_entity_id
        WavveProgramEntity.current_entity_id += 1
        self.episode_code = episode_code
        self.quality = quality
        self.ffmpeg_status = -1
        self.ffmpeg_status_kor = u'대기중'
        self.ffmpeg_percent = 0
        self.created_time = datetime.now().strftime('%m-%d %H:%M:%S')
        self.completed_time = '01-01 00:00:00' # for db
        self.completed = False     # for db
        self.json_data = None
        self.ffmpeg_arg = None
        self.cancel = False
        WavveProgramEntity.entity_list.append(self)
    
    def __getitem__(self, key):
        return getattr(self, key)

    @staticmethod
    def get_entity(entity_id):
        for _ in WavveProgramEntity.entity_list:
            if _.entity_id == entity_id:
                return _
        return None


class LogicProgram(object):
    recent_code = None

    # 다운로드 목록
    download_queue = None

    download_thread = None

    current_ffmpeg_count = 0


    @staticmethod
    def start():
        try:
            if LogicProgram.download_queue is None:
                LogicProgram.download_queue = Queue.Queue()
            
            if LogicProgram.download_thread is None:
                LogicProgram.download_thread = threading.Thread(target=LogicProgram.download_thread_function, args=())
                LogicProgram.download_thread.daemon = True  
                LogicProgram.download_thread.start()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def download_program(req):
        try:
            episode_code = req.form['code']
            quality = req.form['quality']

            ### edit by lapis
            ### check if item is in db
            if req.form['pass'] == 'false' and ModelWavveProgram.is_duplicate(episode_code, quality):
                return 'already'
            ###
            ModelWavveProgram.append({
                "episode_code": episode_code,
                "quality": quality
            })
            ###

            LogicProgram.download_program2(episode_code, quality)
            return 'success'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return 'fail'

    @staticmethod
    def download_program2(episode_code, quality):
        try:
            LogicProgram.start()
            entity = WavveProgramEntity(episode_code, quality)
            entity.json_data = Wavve.vod_contents_contentid(episode_code)

            ### edit by lapis
            ModelWavveProgram.update(entity)
            ###

            #entity.json_data['filename'] = Wavve.get_filename(entity.json_data, quality)
            LogicProgram.download_queue.put(entity)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def download_thread_function():
        while True:
            try:
                while True:
                    if LogicProgram.current_ffmpeg_count < int(ModelSetting.get('program_auto_count_ffmpeg')):
                        break
                    time.sleep(5)

                entity = LogicProgram.download_queue.get()
                if entity.cancel:
                    continue
                # 초기화
                if entity is None:
                    return

                contenttype = 'onairvod' if entity.json_data['type'] == 'onair' else 'vod'
                count = 0
                while True:
                    count += 1
                    streaming_data = Wavve.streaming(contenttype, entity.episode_code, entity.quality, ModelSetting.get('credential'))
                    try:
                        tmp = data2['playurl']
                    except:
                        try:
                            from .logic_basic import LogicBasic
                            LogicBasic.login()
                            streaming_data = Wavve.streaming(contenttype, entity.episode_code, entity.quality, ModelSetting.get('credential'))
                        except:
                            pass

                    entity.json_data['filename'] = Wavve.get_filename(entity.json_data, streaming_data['quality'])
                    if streaming_data is not None:
                        break
                    else:
                        time.sleep(20)
                    if count > 10:
                        entity.ffmpeg_status_kor = u'URL실패'
                        break
                if streaming_data is None:
                    continue

                import ffmpeg
                max_pf_count = ModelSetting.get('max_pf_count')
                save_path = ModelSetting.get('program_auto_path')
                if ModelSetting.get('program_auto_make_folder') == 'True':
                    program_path = os.path.join(save_path, entity.json_data['programtitle'])
                    save_path = program_path
                try:
                    if not os.path.exists(save_path):
                        os.makedirs(save_path)
                except:
                    logger.debug('program path make fail!!')
                
                ### edit by lapis
                ModelWavveProgram.update(entity)
                ###

                # 파일 존재여부 체크
                if os.path.exists(os.path.join(save_path, entity.json_data['filename'])):
                    entity.ffmpeg_status_kor = '파일 있음'
                    entity.ffmpeg_percent = 100
                    ### edit by lapis
                    ModelWavveProgram.delete(entity.episode_code, entity.quality)
                    ###
                    plugin.socketio_list_refresh()
                    continue

                tmp = Wavve.get_prefer_url(streaming_data['playurl'])
                f = ffmpeg.Ffmpeg(tmp, entity.json_data['filename'], plugin_id=entity.entity_id, listener=LogicProgram.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='wavve_program', save_path=save_path)
                f.start()
                LogicProgram.current_ffmpeg_count += 1
                LogicProgram.download_queue.task_done()                

            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        

    @staticmethod
    def ffmpeg_listener(**arg):
        #logger.debug(arg)
        import ffmpeg
        refresh_type = None
        if arg['type'] == 'status_change':
            if arg['status'] == ffmpeg.Status.DOWNLOADING:
                pass
            elif arg['status'] == ffmpeg.Status.COMPLETED:
                pass
            elif arg['status'] == ffmpeg.Status.READY:
                pass
        elif arg['type'] == 'last':
            LogicProgram.current_ffmpeg_count += -1
        elif arg['type'] == 'log':
            pass
        elif arg['type'] == 'normal':
            pass
        if refresh_type is not None:
            pass

        entity = WavveProgramEntity.get_entity(arg['plugin_id'])
        if entity is None:
            return
        entity.ffmpeg_arg = arg
        entity.ffmpeg_status = int(arg['status'])
        entity.ffmpeg_status_kor = str(arg['status'])
        entity.ffmpeg_percent = arg['data']['percent']

        ### edit by lapis
        if entity.ffmpeg_status == 7 or \
           entity.ffmpeg_percent == 100 or \
           entity.ffmpeg_status_kor in ['완료']:
                entity.completed = True
                entity.completed_time = datetime.now().strftime('%m-%d %H:%M:%S')
                ModelWavveProgram.update(entity)
        ###

        import plugin
        arg['status'] = str(arg['status'])
        plugin.socketio_callback('status', arg)
    

    @staticmethod
    def program_auto_command(req):
        try:
            command = req.form['command']
            entity_id = int(req.form['entity_id'])
            logger.debug('command :%s %s', command, entity_id)
            entity = WavveProgramEntity.get_entity(entity_id)
            
            ret = {}
            if command == 'cancel':
                if entity.ffmpeg_status == -1:
                    entity.cancel = True
                    entity.ffmpeg_status_kor = "취소"
                    plugin.socketio_list_refresh()
                    ret['ret'] = 'refresh'
                elif entity.ffmpeg_status != 5:
                    ret['ret'] = 'notify'
                    ret['log'] = '다운로드중 상태가 아닙니다.'
                else:
                    idx = entity.ffmpeg_arg['data']['idx']
                    import ffmpeg
                    ffmpeg.Ffmpeg.stop_by_idx(idx)
                    #plugin.socketio_list_refresh()
                    ret['ret'] = 'refresh'
                
                ### edit by lapis
                ModelWavveProgram.delete(entity.episode_code, entity.quality)
                ### 
            elif command == 'reset':
                if LogicProgram.download_queue is not None:
                    with LogicProgram.download_queue.mutex:
                        LogicProgram.download_queue.queue.clear()
                    for _ in WavveProgramEntity.entity_list:
                        if _.ffmpeg_status == 5:
                            import ffmpeg
                            idx = _.ffmpeg_arg['data']['idx']
                            ffmpeg.Ffmpeg.stop_by_idx(idx)
                WavveProgramEntity.entity_list = []
                plugin.socketio_list_refresh()
                ret['ret'] = 'refresh'
            elif command == 'delete_completed':
                new_list = []
                for _ in WavveProgramEntity.entity_list:
                    if _.ffmpeg_status_kor in ['파일 있음', '취소', 'URL실패']:
                        continue
                    if _.ffmpeg_status != 7:
                        new_list.append(_)
                WavveProgramEntity.entity_list = new_list
                plugin.socketio_list_refresh()
                ret['ret'] = 'refresh'

            
            
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'notify'
            ret['log'] = str(e)
        return ret

    ### edit by lapis
    @staticmethod
    def program_list_command(req):
        try:
            from flask_socketio import SocketIO, emit, send
            
            logger.debug('command :%s', req)

            ret = {}

            if req.form['cmd'] == 'remove_completed':
                ModelWavveProgram.remove_completed()
            elif req.form['cmd'] == 'remove_one':
                episode_code, quality = req.form['val'].split(',')
                ModelWavveProgram.delete(episode_code, quality)

            ret = ModelWavveProgram.filelist(req)
            ret['ret'] = 'refresh'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = {}
            ret['ret'] = 'notify'
            ret['log'] = str(e)
        return ret
    ###

    @staticmethod
    def download_program_check(req):
        ret = {}
        try:
            logger.debug(req.form)
            data = req.form['data']
            logger.debug(data)

            lists = data[:-1].split(',')
            count = 0
            for _ in lists:
                code, quality = _.split('|')
                LogicProgram.download_program2(code, quality)
                count += 1
            ret['ret'] = 'success'
            ret['log'] = count
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'fail'
            ret['log'] = str(e)
        return ret

    ### edit by lapis
    @staticmethod
    def retry_download_failed():
        failed_list = ModelWavveProgram.get_failed()
        for item in failed_list:
            episode_code = item.episode_code
            quality = item.quality
            LogicProgram.download_program2(episode_code, quality)
    ### 
