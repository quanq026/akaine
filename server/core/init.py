import os
import sys
from hashlib import sha256
from importlib import import_module
from json import dumps, load
from shutil import copy, copy2
from traceback import format_exc

from core.bundle import BundleParser
from core.config_manager import Config
from core.constant import ARCAEA_DATABASE_VERSION, ARCAEA_LOG_DATBASE_VERSION
from core.content_grants import grant_missing_full_characters
from core.course import Course
from core.download import DownloadList
from core.purchase import Purchase
from core.sql import (Connect, DatabaseMigrator, LogDatabaseMigrator,
                      MemoryDatabase)
from core.util import try_rename
from core.world import MapParser


class DatabaseInit:
    def __init__(self, db_path: str = Config.SQLITE_DATABASE_PATH, init_folder_path: str = Config.DATABASE_INIT_PATH) -> None:
        self.db_path = db_path
        self.init_folder_path = init_folder_path
        self.c = None
        self.init_data = None

    @property
    def sql_path(self) -> str:
        return os.path.join(self.init_folder_path, 'tables.sql')

    @property
    def course_path(self) -> str:
        return os.path.join(self.init_folder_path, 'courses.json')

    @property
    def pack_path(self) -> str:
        return os.path.join(self.init_folder_path, 'packs.json')

    @property
    def single_path(self) -> str:
        return os.path.join(self.init_folder_path, 'singles.json')

    def table_init(self) -> None:
        '''初始化数据库结构'''
        with open(self.sql_path, 'r', encoding='utf-8') as f:
            self.c.executescript(f.read())
        self.c.execute('''insert into config values("version", :a);''', {
            'a': ARCAEA_DATABASE_VERSION})

    def character_init(self) -> None:
        '''初始化搭档信息'''
        uncapped_characters = self.init_data.char_core.keys()
        for i in range(0, len(self.init_data.char)):
            skill_requires_uncap = 1 if i == 2 else 0
            if i in uncapped_characters:
                max_level = 30
                uncapable = 1
            else:
                max_level = 20
                uncapable = 0
            sql = '''insert into character values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
            self.c.execute(sql, (i, self.init_data.char[i], max_level, self.init_data.frag1[i], self.init_data.prog1[i], self.init_data.overdrive1[i], self.init_data.frag20[i], self.init_data.prog20[i], self.init_data.overdrive20[i],
                                 self.init_data.frag30[i], self.init_data.prog30[i], self.init_data.overdrive30[i], self.init_data.skill_id[i], self.init_data.skill_unlock_level[i], skill_requires_uncap, self.init_data.skill_id_uncap[i], self.init_data.char_type[i], uncapable))

        self.c.execute('''insert into character values(?,?,20,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)''', (
            99, 'shirahime', 38, 33, 28, 66, 58, 50, 66, 58, 50, 'frags_preferred_song', 0, 0, '', 0))

        self.c.execute('''insert into character values(?,?,20,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)''', (
            97, 'saya_konzetsu', 54, 71, 51.5, 125, 160, 120,
            125, 160, 120, 'skill_saya_konzetsu', 0, 0, '', 2))

        self.c.execute('''insert into character values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            98, 'insight_konzetsu', 20, 63, 92.5, 59.5, 85, 125, 80,
            85, 125, 80, 'skill_insight_konzetsu', 0, 0, '', 4, 0))

        for i in self.init_data.char_core:
            self.c.executemany('''insert into char_item values(?,?,'core',?)''', [
                (i, j['core_id'], j['amount']) for j in self.init_data.char_core[i]])
        self.client_7_1_character_init()

    def client_7_1_character_init(self) -> None:
        """Apply canonical candidate definitions in the caller's transaction."""
        if Config.CLIENT_7_1_ENABLED is not True:
            return
        if not self.c.connection.in_transaction:
            raise RuntimeError('Character seeding requires a caller-owned transaction')
        with open(os.path.join(self.init_folder_path, 'client7_1_characters.json'), 'rb') as stream:
            seed = load(stream)
        # Pin the canonical rows independently of JSON formatting or operator paths.
        if (not isinstance(seed, dict) or seed.get('schema') != 'akaine.character-seed-input.v1'
                or seed.get('application_version') != '7.1.0'
                or seed.get('retained_character_ids') != [98]
                or seed.get('new_character_ids') != [100, 101]
                or seed.get('source_member') != 'assets/char/characters.json'
                or seed.get('source_sha256') != '01f199b78a31bfdfc37354e25270bbf841d55c234136ed37ffcf83f50d91e36d'
                or sha256(dumps(seed.get('characters'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                != 'd7b48c707d32e40818e8d7cc3f2cef45823f74ac3b5acf01221a4034cc0e561a'):
            raise ValueError('The canonical 7.1 character seed differs')
        character_columns = self.c.execute('PRAGMA table_info(character)').fetchall()
        if ([column[1] for column in character_columns] !=
                'character_id name max_level frag1 prog1 overdrive1 frag20 prog20 overdrive20 frag30 prog30 overdrive30 skill_id skill_unlock_level skill_requires_uncap skill_id_uncap char_type is_uncapped'.split()
                or [column[1] for column in character_columns if column[5]] != ['character_id']):
            raise ValueError('The 7.1 character definition schema differs')
        # Canonical Maya71 in the hash-qualified source above; no stats or grants change here.
        maya = self.c.execute('SELECT name,skill_id,skill_id_uncap FROM character WHERE character_id=71').fetchone()
        if (maya is None or not isinstance(maya[0], str) or maya[0].lower() != 'maya'
                or maya[1] != 'skill_maya' or maya[2] not in ('', 'skill_maya_uncap')):
            raise ValueError('Conflicting Maya awakening definition')
        self.c.execute("UPDATE character SET skill_id_uncap='skill_maya_uncap' WHERE character_id=71 AND skill_id_uncap=''")
        rows = [(row['character_id'], row['name'], 20,
                 row['base_frag'], row['base_prog'], row['base_over'],
                 row['max_frag'], row['max_prog'], row['max_over'],
                 row['max_frag'], row['max_prog'], row['max_over'],
                 row['skill_id'], row['skill_unlock_level'], 0, '', row['char_type'], 0)
                for row in seed['characters']]
        for row in rows:
            existing = self.c.execute('SELECT * FROM character WHERE character_id=?', (row[0],)).fetchone()
            if existing is not None and tuple(existing) != row:
                raise ValueError(f'Conflicting 7.1 character definition: {row[0]}')
        self.c.executemany('INSERT OR IGNORE INTO character VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        if Config.CHARACTER_FULL_UNLOCK:
            for table in ('user_char', 'user_char_full'):
                columns = self.c.execute('PRAGMA table_info(' + table + ')').fetchall()
                if ([column[1] for column in columns] !=
                        'user_id character_id level exp is_uncapped is_uncapped_override skill_flag'.split()
                        or [column[1] for column in columns if column[5]] != ['user_id', 'character_id']):
                    raise ValueError('The 7.1 user character schema differs')
                flags = self.c.execute('SELECT is_uncapped,is_uncapped_override,skill_flag FROM ' + table + ' WHERE character_id=71').fetchall()
                if any(type(value) is not int or value not in (0, 1) for row in flags for value in row):
                    raise ValueError('Unknown Maya awakening flags')
            flags = self.c.execute('SELECT is_char_uncapped,is_char_uncapped_override FROM user WHERE character_id=71').fetchall()
            if any(type(value) is not int or value not in (0, 1) for row in flags for value in row):
                raise ValueError('Unknown equipped Maya flags')
            for user_id, in self.c.execute('SELECT user_id FROM user').fetchall():
                grant_missing_full_characters(self.c, user_id)
            # A persisted normal grant repairs only its full representation, retaining the chosen override.
            self.c.execute('''UPDATE user_char_full SET is_uncapped=1
                WHERE character_id=71 AND is_uncapped=0 AND EXISTS
                (SELECT 1 FROM user_char n JOIN user u ON u.user_id=n.user_id
                 WHERE n.user_id=user_char_full.user_id AND n.character_id=71 AND n.is_uncapped=1)''')
            self.c.execute('''UPDATE user SET is_char_uncapped=1
                WHERE character_id=71 AND is_char_uncapped=0 AND EXISTS
                (SELECT 1 FROM user_char n JOIN user_char_full f
                 ON f.user_id=n.user_id AND f.character_id=n.character_id
                 WHERE n.user_id=user.user_id AND n.character_id=71 AND n.is_uncapped=1 AND f.is_uncapped=1)''')

    def insert_purchase_item(self, purchases: list):
        '''处理singles和packs'''
        for i in purchases:
            x = Purchase(self.c).from_dict(i)
            x.insert_all()

    def item_init(self) -> None:
        '''初始化物品信息'''
        self.c.executemany('''insert into item values(?,"core",1)''',
                           [(i,) for i in self.init_data.cores])
        self.c.executemany('''insert into item values(?,"world_song",1)''', [
            (i,) for i in self.init_data.world_songs])
        self.c.executemany('''insert into item values(?,"world_unlock",1)''', [
            (i,) for i in self.init_data.world_unlocks])
        self.c.executemany('''insert into item values(?,"course_banner",1)''', [
            (i,) for i in self.init_data.course_banners])

        self.c.execute('''insert into item values(?,?,?)''',
                       ('fragment', 'fragment', 1))
        self.c.execute('''insert into item values(?,?,?)''',
                       ('memory', 'memory', 1))
        self.c.execute('''insert into item values(?,?,?)''',
                       ('anni5tix', 'anni5tix', 1))
        self.c.execute('''insert into item values(?,?,?)''',
                       ('pick_ticket', 'pick_ticket', 1))

        with open(self.pack_path, 'rb') as f:
            self.insert_purchase_item(load(f))

        with open(self.single_path, 'rb') as f:
            self.insert_purchase_item(load(f))

        self.c.execute('''insert into item values(?,?,?)''',  # 新手任务奖励曲
                       ('innocence', 'world_song', 1))

    def course_init(self) -> None:
        '''初始化课题信息'''
        courses = []
        with open(self.course_path, 'rb') as f:
            courses = load(f)
        for i in courses:
            x = Course(self.c).from_dict(i)
            x.insert_all()

    def role_power_init(self) -> None:
        '''初始化power和role'''
        self.c.executemany('''insert into role values(?,?)''', [(
            self.init_data.role[i], self.init_data.role_caption[i]) for i in range(len(self.init_data.role))])

        self.c.executemany('''insert into power values(?,?)''', [(
            self.init_data.power[i], self.init_data.power_caption[i]) for i in range(len(self.init_data.power))])

        for i in self.init_data.role_power:
            self.c.executemany('''insert into role_power values(?,?)''', [
                               (i, j) for j in self.init_data.role_power[i]])

    def init(self) -> None:
        sys.path.append(os.path.join(sys.path[0], self.init_folder_path))
        self.init_data = import_module('arc_data').InitData

        with Connect(self.db_path) as c:
            self.c = c
            self.table_init()
            self.character_init()
            self.item_init()
            self.course_init()
            self.role_power_init()


class LogDatabaseInit:
    def __init__(self, db_path: str = Config.SQLITE_LOG_DATABASE_PATH, init_folder_path: str = Config.DATABASE_INIT_PATH) -> None:
        self.db_path = db_path
        self.init_folder_path = init_folder_path
        self.c = None

    @property
    def sql_path(self) -> str:
        return os.path.join(self.init_folder_path, 'log_tables.sql')

    def table_init(self) -> None:
        '''初始化数据库结构'''
        with open(self.sql_path, 'r') as f:
            self.c.executescript(f.read())
        self.c.execute(
            '''insert into cache values("version", :a, -1);''', {'a': ARCAEA_LOG_DATBASE_VERSION})

    def init(self) -> None:
        with Connect(self.db_path) as c:
            self.c = c
            self.table_init()


class DeletedDatabaseInit(DatabaseInit):
    def __init__(self, db_path: str = Config.SQLITE_DATABASE_DELETED_PATH) -> None:
        super().__init__(db_path)

    def init(self) -> None:
        with Connect(self.db_path) as c:
            self.c = c
            self.table_init()


class FileChecker:
    '''文件检查及初始化类'''

    def __init__(self, logger=None):
        self.logger = logger

    def check_file(self, file_path: str) -> bool:
        f = os.path.isfile(file_path)
        if not f:
            self.logger.warning('File `%s` is missing.' % file_path)
        return f

    def check_folder(self, folder_path: str) -> bool:
        f = os.path.isdir(folder_path)
        if not f:
            self.logger.warning('Folder `%s` is missing.' % folder_path)
        return f

    def _check_update_database_log(self) -> bool:
        if not self.check_file(Config.SQLITE_LOG_DATABASE_PATH):
            # 新建日志数据库
            try:
                self.logger.info(
                    f'Try to new the file {Config.SQLITE_LOG_DATABASE_PATH}')
                LogDatabaseInit().init()
                self.logger.info(
                    f'Success to new the file {Config.SQLITE_LOG_DATABASE_PATH}')
            except Exception as e:
                self.logger.error(format_exc())
                self.logger.error(
                    f'Failed to new the file {Config.SQLITE_LOG_DATABASE_PATH}')
                return False
        else:
            # 检查更新
            with Connect(Config.SQLITE_LOG_DATABASE_PATH) as c:
                try:
                    x = c.execute(
                        '''select value from cache where key="version"''').fetchone()
                except:
                    x = None
            if not x or x[0] != ARCAEA_LOG_DATBASE_VERSION:
                self.logger.warning(
                    f'Maybe the file `{Config.SQLITE_LOG_DATABASE_PATH}` is an old version.')
                try:
                    self.logger.info(
                        f'Try to update the file `{Config.SQLITE_LOG_DATABASE_PATH}`')
                    self.update_log_database()
                    self.logger.info(
                        f'Success to update the file `{Config.SQLITE_LOG_DATABASE_PATH}`')
                except Exception as e:
                    self.logger.error(format_exc())
                    self.logger.error(
                        f'Failed to update the file `{Config.SQLITE_LOG_DATABASE_PATH}`')
                    return False

        return True

    def _check_update_database_main(self, db_path=Config.SQLITE_DATABASE_PATH, init_class=DatabaseInit) -> bool:
        if not self.check_file(db_path):
            # 新建数据库
            try:
                self.logger.info(f'Try to new the file `{db_path}`.')
                init_class().init()
                self.logger.info(f'Success to new the file `{db_path}`.')
            except Exception as e:
                self.logger.error(format_exc())
                self.logger.warning(f'Failed to new the file `{db_path}`.')
                return False
        else:
            # 检查更新
            with Connect(db_path) as c:
                try:
                    c.execute('''select value from config where id="version"''')
                    x = c.fetchone()
                except:
                    x = None
            # 数据库自动更新，不强求
            if not x or x[0] != ARCAEA_DATABASE_VERSION:
                self.logger.warning(
                    f'Maybe the file `{db_path}` is an old version. Version: {x[0] if x else "None"}')
                if Config.CLIENT_7_1_ENABLED is True:
                    self.logger.error('The 7.1 candidate requires a reviewed current-schema database; automatic migration is blocked.')
                    return False
                try:
                    self.logger.info(
                        f'Try to update the file `{db_path}` to version {ARCAEA_DATABASE_VERSION}.')

                    if not os.path.isdir(Config.SQLITE_DATABASE_BACKUP_FOLDER_PATH):
                        os.makedirs(Config.SQLITE_DATABASE_BACKUP_FOLDER_PATH)

                    backup_path = try_rename(db_path, os.path.join(
                        Config.SQLITE_DATABASE_BACKUP_FOLDER_PATH, os.path.split(db_path)[-1] + '.bak'))

                    try:
                        copy2(backup_path, db_path)
                    except:
                        copy(backup_path, db_path)

                    temp_path = os.path.join(
                        *os.path.split(db_path)[:-1], 'old_arcaea_database.db')
                    if os.path.isfile(temp_path):
                        os.remove(temp_path)

                    try_rename(db_path, temp_path)

                    init_class().init()
                    self.update_database(temp_path, db_path)

                    self.logger.info(
                        f'Success to update the file `{db_path}`.')

                except Exception as e:
                    self.logger.error(format_exc())
                    self.logger.warning(
                        f'Fail to update the file `{db_path}`.')
                    return False

        return True

    def check_update_database(self) -> bool:
        return (self._check_update_database_main() and self._check_update_database_log()
                and self._check_update_database_main(Config.SQLITE_DATABASE_DELETED_PATH, DeletedDatabaseInit)
                and self.check_client_7_1_characters())

    def check_client_7_1_characters(self) -> bool:
        if Config.CLIENT_7_1_ENABLED is not True:
            return True
        success = False
        try:
            with Connect(Config.SQLITE_DATABASE_PATH, logger=self.logger) as cursor:
                cursor.execute('BEGIN IMMEDIATE')
                initializer = DatabaseInit(Config.SQLITE_DATABASE_PATH, Config.DATABASE_INIT_PATH)
                initializer.c = cursor
                initializer.client_7_1_character_init()
                # Connect rolls back and suppresses non-ArcError failures.
                success = True
        except Exception:
            self.logger.error(format_exc())
            return False
        return success

    @staticmethod
    def update_database(old_path: str, new_path: str = Config.SQLITE_DATABASE_PATH) -> None:
        '''更新数据库，并删除旧文件'''
        if os.path.isfile(old_path) and os.path.isfile(new_path):
            DatabaseMigrator(old_path, new_path).update_database()
            os.remove(old_path)

    @staticmethod
    def update_log_database(old_path: str = Config.SQLITE_LOG_DATABASE_PATH) -> None:
        '''直接更新日志数据库'''
        if os.path.isfile(old_path):
            LogDatabaseMigrator(old_path).update_database()

    def check_song_file(self) -> bool:
        '''检查song有关文件并初始化缓存'''
        f = self.check_folder(Config.SONG_FILE_FOLDER_PATH)
        self.logger.info("Initialize song data...")
        try:
            DownloadList.initialize_cache()
            if not Config.SONG_FILE_HASH_PRE_CALCULATE:
                self.logger.info('Song file hash pre-calculate is disabled.')
        except Exception as e:
            self.logger.error(format_exc())
            self.logger.warning('Song data initialization error!')
            f = False
        return f

    def check_content_bundle(self) -> bool:
        '''检查 content bundle 有关文件并初始化缓存'''
        f = self.check_folder(Config.CONTENT_BUNDLE_FOLDER_PATH)
        self.logger.info("Initialize content bundle data...")
        try:
            BundleParser()
        except Exception as e:
            self.logger.error(format_exc())
            self.logger.warning('Content bundle data initialization error!')
            f = False
        return f

    def check_world_map(self) -> bool:
        '''检查 world map 有关文件并初始化缓存'''
        f = self.check_folder(Config.WORLD_MAP_FOLDER_PATH)
        self.logger.info("Initialize world map data...")
        try:
            MapParser()
        except Exception as e:
            self.logger.error(format_exc())
            self.logger.warning('World map data initialization error!')
            f = False
        return f

    def check_before_run(self) -> bool:
        '''运行前检查，返回布尔值'''
        MemoryDatabase()  # 初始化内存数据库
        return self.check_song_file() and self.check_content_bundle() and self.check_update_database() and self.check_world_map()
