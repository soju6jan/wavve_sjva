# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
from datetime import datetime
import json

# third-party
from sqlalchemy import or_, and_, func, not_, desc
from sqlalchemy.orm import backref

# sjva 공용
from framework import db, path_app_root, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
#########################################################


db_file = os.path.join(path_app_root, 'data', 'db', '%s.db' % package_name)
app.config['SQLALCHEMY_BINDS'][package_name] = 'sqlite:///%s' % (db_file)

class ModelSetting(db.Model):
    __tablename__ = 'plugin_%s_setting' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String, nullable=False)
 
    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        return {x.name: getattr(self, x.name) for x in self.__table__.columns}

    @staticmethod
    def get(key):
        try:
            return db.session.query(ModelSetting).filter_by(key=key).first().value.strip()
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())
            
    
    @staticmethod
    def get_int(key):
        try:
            return int(ModelSetting.get(key))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def get_bool(key):
        try:
            return (ModelSetting.get(key) == 'True')
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def set(key, value):
        try:
            item = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            if item is not None:
                item.value = value.strip()
                db.session.commit()
            else:
                db.session.add(ModelSetting(key, value.strip()))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def to_dict():
        try:
            ret = Util.db_list_to_dict(db.session.query(ModelSetting).all())
            ret['package_name'] = package_name
            return ret 
        except Exception as e:
            logger.error('Exception:%s ', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                if key in ['scheduler', 'is_running']:
                    continue
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True                  
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.debug('Error Key:%s Value:%s', key, value)
            return False

#########################################################


class ModelWavveEpisode(db.Model):
    __tablename__ = 'plugin_%s_auto_episode' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    contents_json = db.Column(db.JSON)
    streaming_json = db.Column(db.JSON)
    created_time = db.Column(db.DateTime)

    channelname = db.Column(db.String)
    
    programid = db.Column(db.String)
    programtitle = db.Column(db.String)
    
    contentid = db.Column(db.String)
    releasedate = db.Column(db.String)
    episodenumber = db.Column(db.String)
    episodetitle = db.Column(db.String)
    quality = db.Column(db.String)

    vod_type = db.Column(db.String) #general onair
    image = db.Column(db.String)
    playurl = db.Column(db.String)
    
    filename = db.Column(db.String)
    duration = db.Column(db.Integer)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    download_time = db.Column(db.Integer)
    completed = db.Column(db.Boolean)
    user_abort = db.Column(db.Boolean)
    pf_abort = db.Column(db.Boolean)
    etc_abort = db.Column(db.Integer) #ffmpeg 원인 1, 채널, 프로그램
    ffmpeg_status = db.Column(db.Integer)
    temp_path = db.Column(db.String)
    save_path = db.Column(db.String)
    pf = db.Column(db.Integer)
    retry = db.Column(db.Integer)
    filesize = db.Column(db.Integer)
    filesize_str = db.Column(db.String)
    download_speed = db.Column(db.String)
    call = db.Column(db.String)

    def __init__(self, call, info, streaming):
        self.created_time = datetime.now()
        self.completed = False
        self.user_abort = False
        self.pf_abort = False
        self.etc_abort = 0
        self.ffmpeg_status = -1
        self.pf = 0
        self.retry = 0
        self.call = call
        self.set_info(info)
        self.set_streaming(streaming)


    def __repr__(self):
        #return "<Episode(id:%s, episode_code:%s, quality:%s)>" % (self.id, self.episode_code, self.quality)
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%m-%d %H:%M:%S') if self.created_time is not None else ''
        ret['start_time'] = self.start_time.strftime('%m-%d %H:%M:%S') if self.start_time is not None else ''
        ret['end_time'] = self.end_time.strftime('%m-%d %H:%M:%S') if self.end_time is not None else ''
        return ret

    def set_info(self, data):
        self.contents_json = data
        self.channelname = data['channelname']
        
        self.programid = data['programid']
        self.programtitle = data['programtitle']
        
        self.contentid = data['contentid']
        self.releasedate = data['releasedate']
        self.episodenumber = data['episodenumber']
        self.episodetitle = data['episodetitle']
        self.image = 'https://' + data['image']
        self.vod_type = data['type']

    def set_streaming(self, data):
        self.streaming_json = data
        self.playurl = data['playurl']
        import framework.wavve.api as Wavve
        self.filename = Wavve.get_filename(self.contents_json, data['quality'])
        self.quality = data['quality']


# edit by lapis
# 20200925
class ModelWavveProgram(db.Model):
    __tablename__ = 'plugin_%s_auto_program' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)

    created_time    = db.Column(db.DateTime)
    completed_time  = db.Column(db.DateTime)

    episode_code    = db.Column(db.String)
    program_id    = db.Column(db.String)
    quality         = db.Column(db.String)
    program_title   = db.Column(db.String)
    episode_number  = db.Column(db.String)
    thumbnail       = db.Column(db.String)
    programimage    = db.Column(db.String)

    completed       = db.Column(db.Boolean)
    

    def __init__(self, data):
        self.episode_code   = data['episode_code']
        self.quality        = data['quality']
        self.completed      = False 
        # self.program_title  = data.json_data['programtitle']
        # self.episode_number = data.json_data['episodenumber']
        # self.thumbnail      = data.json_data['image']
        # self.programimage   = data.json_data['programimage']


    def __repr__(self):
        #return "<Episode(id:%s, episode_code:%s, quality:%s)>" % (self.id, self.episode_code, self.quality)
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%m-%d %H:%M:%S') if self.created_time is not None else ''
        ret['completed_time'] = self.completed_time.strftime('%m-%d %H:%M:%S') if self.completed_time is not None else ''
        return ret

    def save(self):
        db.session.add(self)
        db.session.commit()

    @staticmethod
    def set(key, value):
        try:
            item = db.session.query(ModelWavveProgram).filter_by(key=key).with_for_update().first()
            if item is not None:
                item.value = value.strip()
                db.session.commit()
            else:
                db.session.add(ModelWavveProgram(key, value.strip()))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def get(episode_code, quality):
        try:
            return db.session.query(ModelWavveProgram).filter_by(
                episode_code=episode_code,
                quality=quality
            ).first()
        except Exception as e:
            logger.error('Exception:%s %s', e, episode_code)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def get_failed():
        try:
            return db.session.query(ModelWavveProgram).filter_by(
                completed=False
            ).all()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def is_duplicate(episode_code, quality):
        try:
            if ModelWavveProgram.get(episode_code, quality) is not None:
                return True
            return False
        except Exception as e:
            logger.error('Exception:%s %s', e, episode_code)
            logger.error(traceback.format_exc())


    ### only works with completed items.
    @staticmethod
    def delete(episode_code, quality):
        try:
            item = db.session.query(ModelWavveProgram).filter_by(episode_code=episode_code, quality=quality).first()
            if item is not None:
                db.session.delete(item)
                db.session.commit()
            else:
                return False
            return True
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def remove_all(is_completed=True): # to remove_all(True/False)
        try:
            db.session.query(ModelWavveProgram).filter_by(completed=is_completed).delete()
            db.session.commit()
            return True
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @classmethod
    def update(cls, entity):
        item = db.session.query(ModelWavveProgram).filter_by(
                episode_code=entity['episode_code'],
                quality=entity['quality']
            ).with_for_update().first()
        if item is not None:
            item.created_time   = datetime.strptime(entity['created_time'], '%m-%d %H:%M:%S')
            item.program_id     = entity.json_data['programid']
            item.program_title  = entity.json_data['programtitle']
            item.episode_number = entity.json_data['episodenumber']
            item.thumbnail      = entity.json_data['image']
            item.programimage   = entity.json_data['programimage']
            item.completed      = entity['completed']
            item.completed_time = datetime.strptime(entity['completed_time'], '%m-%d %H:%M:%S')
            db.session.commit()
        else:
            ModelWavveProgram.append(entity)

    @classmethod
    def append(cls, q):
        item = ModelWavveProgram(q)
        item.save()
    

    ### codes from bot_downloader_ktv
    @staticmethod
    def filelist(req):
        try:
            ret = {}
            page = 1
            # page_size = ModelSetting.get_int('web_page_size')
            page_size = 20
            job_id = ''
            search = ''
            if 'page' in req.form:
                page = int(req.form['page'])
            if 'search_word' in req.form:
                search = req.form['search_word']
            option = req.form['option'] # all, completed, failed
            order = req.form['order'] if 'order' in req.form else 'desc'

            query = ModelWavveProgram.make_query(search, option, order)
            count = query.count()
            query = query.limit(page_size).offset((page-1)*page_size)
            logger.debug('ModelWavveProgram count:%s', count)
            lists = query.all()
            ret['list'] = [item.as_dict() for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    
    ### codes from bot_downloader_ktv
    @staticmethod
    def make_query(search, option, order):
        query = db.session.query(ModelWavveProgram)
        if search is not None and search != '':
            if search.find('|') != -1:
                tmp = search.split('|')
                conditions = []
                conditions2 = []
                for tt in tmp:
                    if tt != '':
                        conditions.append(ModelWavveProgram.program_title.like('%'+tt.strip()+'%') )
                        conditions2.append(ModelWavveProgram.episode_number.like(tt.strip()))
                query1 = query.filter(or_(*conditions))
                query2 = query.filter(or_(*conditions2))
            elif search.find(',') != -1:
                tmp = search.split(',')
                for tt in tmp:
                    if tt != '':
                        query1 = query.filter(ModelWavveProgram.program_title.like('%'+tt.strip()+'%'))
                        query2 = query.filter(ModelWavveProgram.episode_number.like(tt.strip()))
            else:
                query1 = query.filter(ModelWavveProgram.program_title.like('%'+search+'%'))
                query2 = query.filter(ModelWavveProgram.episode_number.like(search))

            query = query1.union(query2)

        if option == 'completed':
            query = query.filter(ModelWavveProgram.completed == True)
        elif option == 'failed':
            query = query.filter(ModelWavveProgram.completed == False)
        

        if order == 'desc':
            query = query.order_by(desc(ModelWavveProgram.id))
        else:
            query = query.order_by(ModelWavveProgram.id)

        return query


            
    ### codes from bot_downloader_ktv
    ### 작동하는지 확인 안해봄
    @staticmethod
    def itemlist_by_api(req):
        try:
            search = req.args.get('search')
            logger.debug(search)
            option = req.args.get('option')
            order = 'desc'
            count = req.args.get('count')
            if count is None or count == '':
                count = 100
            query = ModelWavveProgram.make_query(search, option, order)
            query = query.limit(count)
            lists = query.all()
            return lists
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())