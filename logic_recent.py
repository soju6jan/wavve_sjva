# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
from datetime import datetime, timedelta
import re

# third-party
from pytz import timezone
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify
from sqlalchemy import desc, or_

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data
from framework.job import Job
from framework.util import Util

# 패키지
import framework.wavve.api as Wavve
import ffmpeg
from .plugin import package_name, logger
from .model import ModelSetting, ModelWavveEpisode
from .logic_basic import LogicBasic



# 로그
#########################################################
        
class LogicRecent(object):
    current_auto_count_ffmpeg = 0

    @staticmethod
    def scheduler_function():
        try:
            logger.debug('Wavve scheduler_function start..')

            page = int(ModelSetting.get('auto_page'))
            max_pf_count = ModelSetting.get('max_pf_count')
            save_path = ModelSetting.get('auto_save_path')
            auto_quality = ModelSetting.get('auto_quality')
            retry_user_abort = (ModelSetting.get('retry_user_abort') == 'True')
            qvod_download = (ModelSetting.get('qvod_download') == 'True')
            except_channel = ModelSetting.get('except_channel')
            except_program = ModelSetting.get('except_program')
            download_program_in_qvod = ModelSetting.get('download_program_in_qvod')
            download_mode = ModelSetting.get('download_mode')
            whitelist_program = ModelSetting.get('whitelist_program') 
            whitelist_first_episode_download = (ModelSetting.get('whitelist_first_episode_download') == 'True')

            except_channels = [x.strip() for x in except_channel.replace('\n', ',').split(',')]
            except_programs = [x.strip().replace(' ', '') for x in except_program.replace('\n', ',').split(',')]
            except_episode_keyword = [x.strip() for x in ModelSetting.get('except_episode_keyword').replace('\n', ',').split(',')]
            download_program_in_qvods = [x.strip().replace(' ', '') for x in download_program_in_qvod.replace('\n', ',').split(',')]
            whitelist_programs = [x.strip().replace(' ', '') for x in whitelist_program.replace('\n', ',').split(',')]
            Util.get_list_except_empty(except_channels)
            
            except_channels = Util.get_list_except_empty(except_channels)
            except_programs = Util.get_list_except_empty(except_programs)
            except_episode_keyword = Util.get_list_except_empty(except_episode_keyword)
            download_program_in_qvods = Util.get_list_except_empty(download_program_in_qvods)
            whitelist_programs = Util.get_list_except_empty(whitelist_programs)

            logger.debug('except_channels:%s', except_channels)
            logger.debug('except_programs:%s', except_programs)
            logger.debug('qvod_download :%s %s', qvod_download, type(qvod_download))
            for i in range(1, page+1):
                vod_list = Wavve.vod_newcontents(page=i)['list']
                #logger.debug(vod_list)
                logger.debug('Page:%s vod len:%s', page, len(vod_list))
                for vod in vod_list:
                    try:
                        while True:
                            if LogicRecent.current_auto_count_ffmpeg < int(ModelSetting.get('auto_count_ffmpeg')):
                                break
                            time.sleep(10)
                            #logger.debug('wavve wait : %s', LogicRecent.current_auto_count_ffmpeg)
                        #logger.debug(vod)
                        contentid = vod["contentid"]
                        contenttype = 'onairvod' if vod['type'] == 'onair' else 'vod'

                        episode = db.session.query(ModelWavveEpisode) \
                            .filter((ModelWavveEpisode.call == 'auto') | (ModelWavveEpisode.call == None)) \
                            .filter_by(contentid=contentid) \
                            .with_for_update().first() \
                                
                        if episode is not None:
                            if episode.completed:
                                continue
                            elif episode.user_abort:
                                if retry_user_abort:
                                    episode.user_abort = False
                                else:
                                    #사용자 중지로 중단했고, 다시받기가 false이면 패스
                                    continue
                            elif episode.etc_abort > 10:
                                # 1:알수없는이유 시작실패, 2 타임오버, 3, 강제스톱.킬
                                # 11:제외채널, 12:제외프로그램
                                # 13:장르제외, 14:화이트리스트 제외, 7:권한없음, 6:화질다름
                                #logger.debug('EPC Abort : %s', episode.etc_abort)
                                continue
                            elif episode.retry > 20:
                                logger.debug('retry 20')
                                episode.etc_abort = 9
                                continue
                        # URL때문에 DB에 있어도 다시 JSON을 받아야함.
                        for episode_try in range(3):
                            json_data = Wavve.streaming(contenttype, contentid, auto_quality)
                            tmp = json_data['playurl']

                            if json_data is None:
                                logger.debug('episode fail.. %s', episode_try)
                                time.sleep(20)
                            else: 
                                break
                        
                        if episode is None:
                            if json_data is None:
                                episode = ModelWavveEpisode('auto', info=vod, streaming=json_data)
                                db.session.add(episode)
                                db.session.commit()
                                continue
                            else:
                                episode = ModelWavveEpisode('auto', info=vod, streaming=json_data)
                                db.session.add(episode)
                        else:
                            if json_data is None:
                                continue
                            else:
                                episode.set_streaming(json_data)
                        if json_data['playurl'].find('preview') != -1:
                            episode.etc_abort = 7
                            db.session.commit()
                            continue
                        
                        # 채널, 프로그램 체크
                        flag_download = True
                        if contenttype == 'onairvod':
                            if not qvod_download:
                                episode.etc_abort = 11
                                flag_download = False
                                for programtitle in download_program_in_qvods:
                                    if episode.programtitle.replace(' ', '').find(programtitle) != -1:
                                        flag_download = True
                                        episode.etc_abort = 0
                                        break
                            # 시간체크
                            if flag_download:
                                logger.debug(episode.episodetitle)
                                match = re.compile(r'Quick\sVOD\s(?P<time>\d{2}\:\d{2})\s').search(episode.episodetitle)
                                if match:
                                    dt_now = datetime.now()
                                    logger.debug(dt_now)
                                    dt_tmp = datetime.strptime(match.group('time'), '%H:%M')
                                    dt_start = datetime(dt_now.year, dt_now.month, dt_now.day, dt_tmp.hour, dt_tmp.minute, 0, 0)
                                    logger.debug(dt_start)
                                    if (dt_now - dt_start).seconds < 0:
                                        dt_start = dt_start + timedelta(days=-1)
                                    #detail = Wavve.vod_contents_contentid(episode.contentid)
                                    if 'detail' not in episode.contents_json:
                                        episode.contents_json['detail'] = Wavve.vod_contents_contentid(episode.contentid)
                                    qvod_playtime = episode.contents_json['detail']['playtime']
                                    delta = (dt_now - dt_start).seconds
                                    if int(qvod_playtime) > delta:
                                        flag_download = False
                                        episode.etc_abort = 8
                                        
                                    logger.debug('QVOD %s %s %s %s', flag_download, match.group('time'), qvod_playtime, delta)
                                else:
                                    logger.debug('QVOD fail..')
                                    flag_download = False
                                    episode.etc_abort = 7
                                

                        if download_mode == '0':
                            for program_name in except_programs:
                                if episode.programtitle.replace(' ', '').find(program_name) != -1:
                                    episode.etc_abort = 13
                                    flag_download = False
                                    break
                            if episode.channelname in except_channels:
                                episode.etc_abort = 12
                                flag_download = False
                        else:
                            if flag_download:
                                find_in_whitelist = False
                                for program_name in whitelist_programs:
                                    if episode.programtitle.replace(' ', '').find(program_name) != -1:
                                        find_in_whitelist = True
                                        break
                                if not find_in_whitelist:
                                    episode.etc_abort = 14
                                    flag_download = False
                            if not flag_download and whitelist_first_episode_download and episode.episodenumber == '1':
                                flag_download = True
                        # 2021-06-26
                        if flag_download and episode.episodenumber is not None and episode.episodenumber != '':
                            for keyword in except_episode_keyword:
                                if episode.episodenumber.find(keyword) != -1:
                                    episode.etc_abort = 15
                                    flag_download = False
                                    break

                        #logger.debug(episode.quality)
                        if flag_download and episode.quality != auto_quality:
                            if auto_quality == '2160p' and episode.quality == '1080p' and ModelSetting.get_bool('2160_receive_1080'):
                                if episode.created_time + timedelta(minutes=ModelSetting.get_int('2160_wait_minute')) < datetime.now():
                                    logger.debug('1080p download')
                                    pass
                                else:
                                    episode.etc_abort = 5
                                    db.session.commit()
                                    continue
                            else:
                                episode.etc_abort = 6
                                db.session.commit()
                                continue

                        if flag_download:
                            episode.etc_abort = 0
                            episode.retry += 1
                            episode.pf = 0 # 재시도
                            episode.save_path = save_path
                            episode.start_time = datetime.now()
                            db.session.commit()
                        else:
                            db.session.commit()
                            continue
                        logger.debug('FFMPEG Start.. id:%s', episode.id)
                        if episode.id is None:
                            logger.debug('PROGRAM:%s', episode.programtitle)
                        tmp = Wavve.get_prefer_url(episode.playurl)

                        f = ffmpeg.Ffmpeg(tmp, episode.filename, plugin_id=episode.id, listener=LogicBasic.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='%s_recent' % package_name, save_path=save_path)
                        f.start()
                        LogicRecent.current_auto_count_ffmpeg += 1
                        #f.start_and_wait()
                        time.sleep(20)
                    
                        #return
                    except Exception as e: 
                        logger.error('Exception:%s', e)
                        logger.error(traceback.format_exc())
                        #db.session.rollback()
                        logger.debug('ROLLBACK!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
                    finally:
                        #logger.debug('wait..')
                        pass
            logger.debug('=======================================')
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_list(req):
        try:
            page_size = 20
            page = int(req.form['page']) if 'page' in req.form else 1
            option = req.form['option'] if 'option' in req.form else 'all'
            order = req.form['order'] if 'order' in req.form else 'desc'
            program = req.form['program'].strip() if 'program' in req.form else None
            #query = Episode.query.filter_by(call='auto')
            query = ModelWavveEpisode.query.filter((ModelWavveEpisode.call == 'auto') | (ModelWavveEpisode.call == None))
            if program is not None:
                #query = query.filter(ModelWavveEpisode.programtitle.like('%'+program+'%'))
                query = query.filter(or_(ModelWavveEpisode.programtitle.like('%'+program+'%'), ModelWavveEpisode.channelname.like('%'+program+'%')))
            if option == 'completed':
                query = query.filter_by(completed=True)
            elif option == 'uncompleted':
                query = query.filter_by(completed=False)
            elif option == 'user_abort':
                query = query.filter_by(user_abort=True)
            elif option == 'pf_abort':
                query = query.filter_by(pf_abort=True)            
            elif option == 'etc_abort_under_10':
                query = query.filter(ModelWavveEpisode.etc_abort < 10, ModelWavveEpisode.etc_abort > 0) 
            elif option == 'etc_abort_11':
                query = query.filter_by(etc_abort='11')            
            elif option == 'etc_abort_12':
                query = query.filter_by(etc_abort='12')
            elif option == 'etc_abort_13':
                query = query.filter_by(etc_abort='13')            
            elif option == 'etc_abort_14':
                query = query.filter_by(etc_abort='14')            
            if order == 'desc':
                query = query.order_by(desc(ModelWavveEpisode.id))
            else:
                query = query.order_by(ModelWavveEpisode.id)
            count = query.count()
            if page_size:
                query = query.limit(page_size)
            if page: 
                query = query.offset((page-1)*page_size)
            tmp = query.all()
            ret = {}
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            ret['list'] = [item.as_dict() for item in tmp]
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def add_condition_list(req):
        try:
            mode = req.form['mode']
            value = req.form['value']
            old_value = ModelSetting.get(mode)
            entity_list = [x.strip().replace(' ', '') for x in old_value.replace('\n', ',').split(',')]
            if value.replace(' ', '') in entity_list:
                db.session.commit() 
                return 0
            else:
                if old_value != '':
                    old_value += ', '
                old_value += value
                ModelSetting.set(mode, old_value)
                return 1
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return -1
        finally:
            pass
    
   
    @staticmethod
    def reset_db():
        try:
            db.session.query(ModelWavveEpisode).delete()
            db.session.commit()
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False
