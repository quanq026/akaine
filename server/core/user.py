import base64
import hashlib
import time
from os import urandom
from random import randint
from json import dumps, loads

from .character import UserCharacter, UserCharacterList
from .config_manager import Config
from .constant import Constant
from .error import (ArcError, DataExist, FriendError, InputError, NoAccess,
                    NoData, RateLimit, UserBan)
from .item import UserItemList
from .limiter import ArcLimiter
from .mission import UserMissionList
from .pack_contract import build_client_pack_list, build_effective_pack_list
from .score import Score, rating_ptt_for_app_version
from .sql import Query, Sql, UserKVTable
from .world import Map, MapParser, UserMap, UserStamina


CURRENT_CLIENT_VERSION = '7.0.255'
CURRENT_ONLY_BANNERS = {
    'online_banner_2026_07',
    'online_banner_2026_08',
    'online_banner_2026_09',
}


def score_rows_for_app_version(rows: list, app_version: str = None) -> list:
    if app_version == CURRENT_CLIENT_VERSION:
        return rows
    return [
        dict(row, song_id='testify1')
        if isinstance(row, dict) and row.get('song_id') == 'testify'
        else row
        for row in rows
    ]


def code_get_id(c, user_code: str) -> int:
    # 用user_code获取user_id

    c.execute('''select user_id from user where user_code = :a''',
              {'a': user_code})
    x = c.fetchone()

    if x is not None:
        user_id = int(x[0])
    else:
        raise NoData('No user.', 401, -3)

    return user_id


class User:
    def __init__(self) -> None:
        self.name: str = None
        self.email: str = None
        self.password: str = None
        self.user_id: int = None
        self.user_code: str = None

        self.join_date = None
        self.rating_ptt: int = None  # 100 times

        self.ticket: int = None
        self.world_rank_score: int = None
        self.ban_flag = None

    @property
    def hash_pwd(self) -> str:
        '''`password`的SHA-256值'''
        return hashlib.sha256(self.password.encode("utf8")).hexdigest()


class UserRegister(User):

    limiter_ip = ArcLimiter(
        Config.GAME_REGISTER_IP_RATE_LIMIT, 'game_register_ip')
    limiter_device = ArcLimiter(
        Config.GAME_REGISTER_DEVICE_RATE_LIMIT, 'game_register_device')

    def __init__(self, c) -> None:
        super().__init__()
        self.c = c

    def set_name(self, name: str):
        if 3 <= len(name) <= 16:
            self.c.execute(
                '''select exists(select * from user where name = :name)''', {'name': name})
            if self.c.fetchone() == (0,):
                self.name = name
            else:
                raise DataExist('Username exists.', 101, -210)

        else:
            raise InputError('Username is invalid.')

    def set_password(self, password: str):
        if 8 <= len(password) <= 32:
            self.password = password
        else:
            raise InputError('Password is invalid.')

    def set_email(self, email: str):
        # 邮箱格式懒得多判断
        if 4 <= len(email) <= 64 and '@' in email and '.' in email:
            self.c.execute(
                '''select exists(select * from user where email = :email)''', {'email': email})
            if self.c.fetchone() == (0,):
                self.email = email
            else:
                raise DataExist('Email address exists.', 102, -211)
        else:
            raise InputError('Email address is invalid.')

    def set_user_code(self, user_code: str) -> None:
        '''设置用户的user_code'''
        if len(user_code) == 9 and user_code.isdigit():
            self.c.execute(
                '''select exists(select * from user where user_code = ?)''', (user_code, ))
            if self.c.fetchone() == (0,):
                self.user_code = user_code
            else:
                raise DataExist('User code exists.', 103, -212)
        else:
            raise InputError('User code is invalid.')

    def _build_user_code(self):
        # 生成9位的user_code，用的自然是随机
        random_times = 0

        while random_times <= 1000:
            random_times += 1
            user_code = ''.join([str(randint(0, 9)) for _ in range(9)])
            self.c.execute('''select exists(select * from user where user_code = :user_code)''',
                           {'user_code': user_code})
            if self.c.fetchone() == (0,):
                break

        if random_times <= 1000:
            self.user_code = user_code
        else:
            raise ArcError('No available user code.')

    def _build_user_id(self):
        # 生成user_id，往后加1
        self.c.execute('''select max(user_id) from user''')
        x = self.c.fetchone()
        if x[0] is not None:
            self.user_id = x[0] + 1
        else:
            self.user_id = 2000001

    def _insert_user_char(self):
        # 为用户添加初始角色
        self.c.execute('''insert into user_char values(?,?,?,?,?,?,0)''',
                       (self.user_id, 0, 1, 0, 0, 0))
        self.c.execute('''insert into user_char values(?,?,?,?,?,?,0)''',
                       (self.user_id, 1, 1, 0, 0, 0))
        self.c.execute(
            '''select character_id, max_level, is_uncapped from character''')
        x = self.c.fetchall()
        if x:
            for i in x:
                exp = 25000 if i[1] == 30 else 10000
                self.c.execute('''insert or replace into user_char_full values(?,?,?,?,?,?,0)''',
                               (self.user_id, i[0], i[1], exp, i[2], 0))

    def register(self, device_id: str = None, ip: str = None):
        if device_id is not None and not self.limiter_device.hit(device_id):
            raise RateLimit(f'''Too many register attempts of device `{
                            device_id}`''', 124, -213)
        if ip is not None and ip != '127.0.0.1' and not self.limiter_ip.hit(ip):
            raise RateLimit(f'''Too many register attempts of ip `{
                            ip}`''', 124, -213)
        now = int(time.time() * 1000)
        if self.user_code is None:
            self._build_user_code()
        if self.user_id is None:
            self._build_user_id()
        self._insert_user_char()

        self.c.execute('''insert into user(user_id, name, password, join_date, user_code, rating_ptt,
        character_id, is_skill_sealed, is_char_uncapped, is_char_uncapped_override, is_hide_rating, favorite_character, max_stamina_notification_enabled, current_map, ticket, prog_boost, email)
        values(:user_id, :name, :password, :join_date, :user_code, 0, 0, 0, 0, 0, 0, -1, 0, '', :memories, 0, :email)
        ''', {'user_code': self.user_code, 'user_id': self.user_id, 'join_date': now, 'name': self.name, 'password': self.hash_pwd, 'memories': Config.DEFAULT_MEMORIES, 'email': self.email})
        self.c.execute('''insert or ignore into user_item(user_id, item_id, type, amount)
                          select :user_id, item_id, type, 1 from item
                          where type = 'course_banner' and is_available = 1''',
                       {'user_id': self.user_id})
        UserMissionList(self.c, self).ensure_bootstrap_missions()


class UserLogin(User):
    # 密码和token的加密方式为 SHA-256
    limiter = ArcLimiter(Config.GAME_LOGIN_RATE_LIMIT, 'game_login')

    def __init__(self, c) -> None:
        super().__init__()
        self.c = c
        self.device_id = None
        self.ip = None
        self.token = None
        self.now = 0

    def set_name(self, name: str):
        self.name = name

    def set_password(self, password: str):
        self.password = password

    def set_device_id(self, device_id: str):
        self.device_id = device_id

    def set_ip(self, ip: str):
        self.ip = ip

    def _arc_auto_ban(self):
        # 多设备自动封号机制，返回封号时长
        self.c.execute('''delete from login where user_id=?''',
                       (self.user_id, ))
        self.c.execute(
            '''select ban_flag from user where user_id=?''', (self.user_id,))
        x = self.c.fetchone()
        if x and x[0] != '' and x[0] is not None:
            last_ban_time = int(x[0].split(':', 1)[0])
            i = 0
            while i < len(Constant.BAN_TIME) - 1 and Constant.BAN_TIME[i] <= last_ban_time:
                i += 1
            ban_time = Constant.BAN_TIME[i]
        else:
            ban_time = Constant.BAN_TIME[0]

        ban_flag = ':'.join(
            (str(ban_time), str(self.now + ban_time * 86400000)))
        self.c.execute('''update user set ban_flag=? where user_id=?''',
                       (ban_flag, self.user_id))

        return ban_time * 86400000

    def _check_device(self, device_list):
        should_delete_num = len(
            device_list) + 1 - Config.LOGIN_DEVICE_NUMBER_LIMIT

        if not Config.ALLOW_LOGIN_SAME_DEVICE:
            if self.device_id in device_list:  # 对相同设备进行删除
                self.c.execute('''delete from login where login_device=:a and user_id=:b''', {
                    'a': self.device_id, 'b': self.user_id})
                should_delete_num = len(
                    device_list) + 1 - device_list.count(self.device_id) - Config.LOGIN_DEVICE_NUMBER_LIMIT

        if should_delete_num >= 1:  # 删掉多余token
            if not Config.ALLOW_LOGIN_SAME_DEVICE and Config.ALLOW_BAN_MULTIDEVICE_USER_AUTO:  # 自动封号检查
                self.c.execute(
                    '''select count(*) from login where user_id=? and login_time>?''', (self.user_id, self.now-86400000))
                if self.c.fetchone()[0] >= Config.LOGIN_DEVICE_NUMBER_LIMIT:
                    remaining_ts = self._arc_auto_ban()
                    raise UserBan('Too many devices logging in during 24 hours.', 105, extra_data={
                                  'remaining_ts': remaining_ts})

            self.c.execute('''delete from login where rowid in (select rowid from login where user_id=:user_id limit :a);''',
                           {'user_id': self.user_id, 'a': int(should_delete_num)})

    def login(self, name: str = '', password: str = '', device_id: str = '', ip: str = ''):
        if name:
            self.set_name(name)
        if password:
            self.set_password(password)
        if device_id:
            self.set_device_id(device_id)
        if ip:
            self.set_ip(ip)

        if not self.limiter.hit(name):
            raise RateLimit(
                f'Too many login attempts of username `{name}`', 123, -203)

        self.c.execute('''select user_id, password, ban_flag from user where name = :name''', {
                       'name': self.name})
        x = self.c.fetchone()
        if x is None:
            raise NoData(f'Username `{self.name}` does not exist.', 104)

        self.user_id = x[0]
        self.now = int(time.time() * 1000)
        if x[2] is not None and x[2] != '':
            # 自动封号检查
            ban_timestamp = int(x[2].split(':', 1)[1])
            if ban_timestamp > self.now:
                raise UserBan(f'Too many devices user `{self.user_id}` logging in during 24 hours.', 105, extra_data={
                              'remaining_ts': ban_timestamp-self.now})

        if x[1] == '':
            # 账号封禁
            raise UserBan(
                f'The account `{self.user_id}` has been banned.', 106)

        if False and x[1] != self.hash_pwd:
            raise NoAccess(f'Wrong password of user `{self.user_id}`', 104)

        self.token = base64.b64encode(hashlib.sha256(
            (str(self.user_id) + str(self.now)).encode("utf8") + urandom(8)).digest()).decode()

        self.c.execute(
            '''select login_device from login where user_id = :user_id''', {"user_id": self.user_id})
        y = self.c.fetchall()
        if y:
            self._check_device([i[0] if i[0] else '' for i in y])

        self.c.execute('''insert into login values(:access_token, :user_id, :time, :ip, :device_id)''', {
            'user_id': self.user_id, 'access_token': self.token, 'device_id': self.device_id, 'time': self.now, 'ip': self.ip})


class UserAuth(User):
    def __init__(self, c) -> None:
        super().__init__()
        self.c = c
        self.token = None

    def token_get_id(self):
        # 用token获取id，没有考虑不同用户token相同情况，说不定会有bug
        self.c.execute('''select user_id from login where access_token = :token''', {
            'token': self.token})
        x = self.c.fetchone()
        if x is not None:
            self.user_id = x[0]
        else:
            raise NoAccess('Wrong token.', -4)

        return self.user_id


class UserInfo(User):
    def __init__(self, c, user_id=None) -> None:
        User.__init__(self)
        self.c = c
        self.user_id = user_id
        self.character = None
        self.is_skill_sealed = False
        self.is_hide_rating = False
        self.recent_score = Score()
        self.favorite_character = None
        self.max_stamina_notification_enabled = False
        self.mp_notification_enabled = True
        self.prog_boost: int = 0
        self.beyond_boost_gauge: float = 0
        self.kanae_stored_prog: float = 0
        self.next_fragstam_ts: int = None
        self.world_mode_locked_end_ts: int = None
        self.current_map: 'Map' = None
        self.stamina: 'UserStamina' = None

        self.insight_state: int = None

        self.custom_banner = None
        self.is_allow_marketing_email = False
        self.is_profile_public = False
        self.showcase_characters = [-1, -1, -1]

        self.__cores: list = None
        self.__db_pack_ids: list = None
        self.__owned_pack_ids: list = None
        self.__packs: list = None
        self.__singles: list = None
        self.characters: 'UserCharacterList' = None
        self.__friends: list = None
        self.__world_unlocks: list = None
        self.__world_songs: list = None
        self.curr_available_maps: list = None
        self.__course_banners: list = None
        self.__fragment: int = None

    @property
    def is_insight_enabled(self) -> bool:
        if self.insight_state is None:
            self.select_user_one_column('insight_state', 4, int)
        return self.insight_state == 3 or self.insight_state == 5

    @property
    def cores(self) -> list:
        if self.__cores is None:
            x = UserItemList(self.c, self).select_from_type('core')
            self.__cores = [{'core_type': i.item_id,
                             'amount': i.amount} for i in x.items]

        return self.__cores

    @property
    def singles(self) -> list:
        if self.__singles is None:
            x = UserItemList(self.c, self).select_from_type('single')
            self.__singles = [i.item_id for i in x.items]

        return self.__singles

    def _get_userpack(self) -> list:
        if self.__db_pack_ids is None:
            x = UserItemList(self.c, self).select_from_type('pack')
            self.__db_pack_ids = [i.item_id for i in x.items]
        return self.__db_pack_ids

    @property
    def owned_pack_ids(self) -> list:
        if self.__owned_pack_ids is None:
            self.__owned_pack_ids = build_effective_pack_list(
                db_packs=self._get_userpack(),
                free_packs=Config.FREE_PACKS,
                custom_pack_ids=Config.CUSTOM_PACK_IDS,
                umbrella_pack_id=Config.CUSTOM_PACK_UMBRELLA,
                client_visible_custom_pack_ids=Config.CLIENT_VISIBLE_CUSTOM_PACK_IDS,
                client_hidden_pack_ids=Config.CLIENT_HIDDEN_PACK_IDS,
            )
        return self.__owned_pack_ids

    def _build_client_pack_list(self, allowed_pack_ids=None) -> list:
        free_packs = Config.FREE_PACKS
        if allowed_pack_ids is not None:
            free_packs = [*free_packs, 'base']
        return build_client_pack_list(
            db_packs=self._get_userpack(),
            free_packs=free_packs,
            custom_pack_ids=Config.CUSTOM_PACK_IDS,
            umbrella_pack_id=Config.CUSTOM_PACK_UMBRELLA,
            max_client_packs=Config.CLIENT_PACK_LIMIT,
            client_visible_custom_pack_ids=Config.CLIENT_VISIBLE_CUSTOM_PACK_IDS,
            client_hidden_pack_ids=Config.CLIENT_HIDDEN_PACK_IDS,
            allowed_pack_ids=allowed_pack_ids,
        )

    @property
    def packs(self) -> list:
        if self.__packs is None:
            self.__packs = list(self._get_userpack())
            self.__packs.extend(
                pack_id for pack_id in Config.FREE_PACKS
                if pack_id not in self.__packs
            )

        return self.__packs

    @property
    def pick_ticket(self) -> int:
        x = UserItemList(self.c, self).select_from_type('pick_ticket')
        if not x.items:
            return 0
        return x.items[0].amount

    @property
    def fragment(self) -> int:
        if self.__fragment is None:
            x = UserItemList(self.c, self).select_from_type('fragment')
            self.__fragment = x.items[0].amount if x.items else 0
        return self.__fragment

    @property
    def world_unlocks(self) -> list:
        if self.__world_unlocks is None:
            x = UserItemList(self.c, self).select_from_type(
                'world_unlock')
            self.__world_unlocks = [i.item_id for i in x.items]

        return self.__world_unlocks

    @property
    def world_songs(self) -> list:
        if self.__world_songs is None:
            x = UserItemList(
                self.c, self).select_from_type('world_song')
            self.__world_songs = [i.item_id for i in x.items]

        return self.__world_songs

    @property
    def course_banners(self) -> list:
        if self.__course_banners is None:
            x = UserItemList(
                self.c, self).select_from_type('course_banner')
            self.__course_banners = [i.item_id for i in x.items]

        return self.__course_banners

    def select_characters(self) -> None:
        self.characters = UserCharacterList(self.c, self)
        self.characters.select_user_characters()

    @property
    def characters_list(self) -> list:
        if self.characters is None:
            self.select_characters()
        return [x.character_id for x in self.characters.characters]

    @property
    def character_displayed(self) -> 'UserCharacter':
        '''对外显示的角色'''
        if self.favorite_character is None:
            return self.character

        self.favorite_character.select_character_uncap_condition(self)
        return self.favorite_character

    @property
    def friend_ids(self) -> list:
        self.c.execute('''select user_id_other from friend where user_id_me = :user_id''', {
            'user_id': self.user_id})
        return self.c.fetchall()

    @property
    def friends(self) -> list:
        # 得到用户的朋友列表
        if self.__friends is None:
            s = []
            for i in self.friend_ids:
                self.c.execute('''select exists(select * from friend where user_id_me = :x and user_id_other = :y)''',
                               {'x': i[0], 'y': self.user_id})

                is_mutual = self.c.fetchone() == (1,)

                you = UserOnline(self.c, i[0])
                you.select_user()
                character = you.character if you.favorite_character is None else you.favorite_character
                character.select_character_uncap_condition(you)

                rating = you.rating_ptt if not you.is_hide_rating else -1

                s.append({
                    "is_mutual": is_mutual,
                    "is_char_uncapped_override": character.is_uncapped_override,
                    "is_char_uncapped": character.is_uncapped,
                    "is_skill_sealed": you.is_skill_sealed,
                    "rating": rating,
                    "join_date": you.join_date,
                    "character": character.character_id,
                    "recent_score": you.recent_score_list,
                    "name": you.name,
                    "user_id": you.user_id
                })
            s.sort(key=lambda item: item["recent_score"][0]["time_played"] if len(
                item["recent_score"]) > 0 else 0, reverse=True)
            self.__friends = s

        return self.__friends

    @property
    def recent_score_list(self) -> list:
        # 用户最近一次成绩，是列表
        if self.name is None:
            self.select_user()

        if self.recent_score.song.song_id is None:
            return []

        self.c.execute('''select best_clear_type from best_score where user_id=:u and song_id=:s and difficulty=:d''', {
            'u': self.user_id, 's': self.recent_score.song.song_id, 'd': self.recent_score.song.difficulty})
        y = self.c.fetchone()
        best_clear_type = y[0] if y is not None else self.recent_score.clear_type

        r = self.recent_score.to_dict()
        r["best_clear_type"] = best_clear_type
        return [r]

    def select_curr_available_maps(self) -> None:
        self.curr_available_maps: list = []
        for i in Config.AVAILABLE_MAP:
            self.curr_available_maps.append(Map(i))

    @property
    def curr_available_maps_list(self) -> list:
        if self.curr_available_maps is None:
            self.select_curr_available_maps()
        return [x.to_dict() for x in self.curr_available_maps]

    def to_dict(self, client_pack_projection=None, app_version=None) -> dict:
        '''返回用户信息的字典，其实就是/user/me'''
        if self.name is None:
            self.select_user()

        packs = self.packs if client_pack_projection is None else \
            self._build_client_pack_list(client_pack_projection)

        # 这是考虑有可能favourite_character设置了用户未拥有的角色，同时提前计算角色列表
        if self.characters is None:
            self.select_characters()
        character_objects = self.characters.characters
        if app_version != CURRENT_CLIENT_VERSION:
            character_objects = [
                character for character in character_objects
                if character.character_id != 97
            ]
        character_list = [character.character_id for character in character_objects]
        if self.favorite_character and self.favorite_character.character_id in character_list:
            favorite_character_id = self.favorite_character.character_id
        else:
            favorite_character_id = -1

        if self.character.character_id not in character_list:
            self.character.character_id = 0

        friends = [dict(
            friend,
            recent_score=score_rows_for_app_version(
                friend.get('recent_score', []), app_version
            ),
        ) for friend in self.friends]
        if app_version == '7.0.255':
            friends = [dict(friend, rating=rating_ptt_for_app_version(
                friend['rating'], app_version)) for friend in friends]

        recent_score = score_rows_for_app_version(
            self.recent_score_list, app_version
        )
        course_banners = self.course_banners
        custom_banner = self.custom_banner
        if app_version != CURRENT_CLIENT_VERSION:
            course_banners = [
                banner for banner in course_banners
                if banner not in CURRENT_ONLY_BANNERS
            ]
            if custom_banner in CURRENT_ONLY_BANNERS:
                custom_banner = ''

        return {
            "is_aprilfools": Config.IS_APRILFOOLS,
            "curr_available_maps": self.curr_available_maps_list,
            "character_stats": [x.to_dict() for x in character_objects],
            "friends": friends,
            "settings": {
                "favorite_character": favorite_character_id,
                "is_hide_rating": self.is_hide_rating,
                "max_stamina_notification_enabled": self.max_stamina_notification_enabled,
                "mp_notification_enabled": self.mp_notification_enabled,
            },
            "user_id": self.user_id,
            "name": self.name,
            "user_code": self.user_code,
            "display_name": self.name,
            "ticket": self.ticket,
            "frag": self.fragment,
            "fragment": self.fragment,
            "fragments": self.fragment,
            "character": self.character.character_id,
            "is_locked_name_duplicate": False,
            "is_skill_sealed": self.is_skill_sealed,
            "current_map": self.current_map.map_id,
            "prog_boost": self.prog_boost,
            "beyond_boost_gauge": self.beyond_boost_gauge,
            "kanae_stored_prog": self.kanae_stored_prog,
            "next_fragstam_ts": self.next_fragstam_ts,
            "max_stamina_ts": self.stamina.max_stamina_ts,
            "stamina": self.stamina.stamina,
            "world_unlocks": self.world_unlocks,
            "world_songs": self.world_songs,
            "singles": self.singles,
            "packs": packs,
            "characters": character_list,
            "cores": self.cores,
            "recent_score": recent_score,
            "max_friend": Constant.MAX_FRIEND_COUNT,
            "rating": rating_ptt_for_app_version(self.rating_ptt, app_version),
            "join_date": self.join_date,
            "global_rank": self.global_rank,
            'country': '',
            'course_banners': course_banners,
            'world_mode_locked_end_ts': self.world_mode_locked_end_ts,
            'locked_char_ids': [],  # [1]
            'user_missions': UserMissionList(self.c, self).select_all().to_dict_list(),
            'pick_ticket': self.pick_ticket,

            # 'custom_banner': 'online_banner_2024_06',
            'custom_banner': custom_banner,
            'is_profile_public': self.is_profile_public,
            'showcase_characters': self.showcase_characters,
            # 'subscription_multiplier': 114,
            # 'memory_boost_ticket': 5,
            'insight_state': self.insight_state,  # 0~2 不可选，3 技能激活，4 未激活，5 激活可选，6 未激活可选

            # 'enabled_features': [
            #     {
            #         "metadata": ["USA"],
            #         "feature": "paymentlink"
            #     }
            # ],
        }

    def from_list(self, x: list) -> 'UserInfo':
        '''从数据库user表全部数据获取信息'''
        if not x:
            return None
        if self.user_id is None:
            self.user_id = x[0]
        self.name = x[1]
        self.join_date = int(x[3])
        self.user_code = x[4]
        self.rating_ptt = x[5]
        self.character = UserCharacter(self.c, x[6])
        self.is_skill_sealed = x[7] == 1
        self.character.is_uncapped = x[8] == 1
        self.character.is_uncapped_override = x[9] == 1
        self.is_hide_rating = x[10] == 1

        self.recent_score.song.song_id = x[11]
        self.recent_score.song.difficulty = x[12]
        self.recent_score.set_score(
            x[13], x[14], x[15], x[16], x[17], x[18], x[19], x[20], x[21])
        self.recent_score.rating = x[22]

        self.favorite_character = None if x[23] == - \
            1 else UserCharacter(self.c, x[23])
        self.max_stamina_notification_enabled = x[24] == 1
        self.current_map = Map(x[25]) if x[25] is not None else Map('')
        self.ticket = x[26]
        self.prog_boost = x[27] if x[27] is not None else 0
        self.email = x[28] if x[28] is not None else ''
        self.world_rank_score = x[29] if x[29] is not None else 0
        self.ban_flag = x[30] if x[30] is not None else ''

        self.next_fragstam_ts = x[31] if x[31] else 0

        self.stamina = UserStamina(self.c, self)
        self.stamina.set_value(x[32], x[33])
        self.world_mode_locked_end_ts = x[34] if x[34] else -1
        self.beyond_boost_gauge = x[35] if x[35] else 0
        self.kanae_stored_prog = x[36] if x[36] else 0

        self.mp_notification_enabled = x[37] == 1

        self.insight_state = x[38]

        self.custom_banner = x[39] if x[39] is not None else ''
        self.is_allow_marketing_email = len(x) > 40 and x[40] == 1
        self.is_profile_public = len(x) > 41 and x[41] == 1
        if len(x) > 42 and x[42] is not None:
            try:
                self.showcase_characters = loads(x[42])
            except Exception:
                self.showcase_characters = [-1, -1, -1]
        if not self.showcase_characters or len(self.showcase_characters) != 3 or not all(isinstance(i, int) for i in self.showcase_characters):
            self.showcase_characters = [-1, -1, -1]

        return self

    def select_user_about_profile(self) -> None:
        self.c.execute(
            '''select custom_banner, is_profile_public, showcase_characters from user where user_id=?''', (self.user_id,))
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        self.custom_banner = x[0] if x[0] is not None else ''
        self.is_profile_public = x[1] == 1
        if x[2] is not None:
            try:
                self.showcase_characters = loads(x[2])
            except Exception:
                self.showcase_characters = [-1, -1, -1]
        if not self.showcase_characters or len(self.showcase_characters) != 3 or not all(isinstance(i, int) for i in self.showcase_characters):
            self.showcase_characters = [-1, -1, -1]

    def select_user(self) -> None:
        # 查user表所有信息
        self.c.execute(
            '''select * from user where user_id = :x''', {'x': self.user_id})
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        self.from_list(x)

    def select_user_about_current_map(self) -> None:
        self.c.execute('''select current_map from user where user_id = :a''',
                       {'a': self.user_id})
        x = self.c.fetchone()
        if x:
            self.current_map = Map(x[0])

    def select_user_about_stamina(self) -> None:
        self.c.execute('''select max_stamina_ts, stamina from user where user_id = :a''',
                       {'a': self.user_id})
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        self.stamina = UserStamina(self.c, self)
        self.stamina.set_value(x[0], x[1])

    def from_list_about_character(self, x: list) -> None:
        '''从数据库user表获取搭档信息'''
        self.name = x[0]
        self.character = UserCharacter(self.c, x[1], self)
        self.is_skill_sealed = x[2] == 1
        self.character.is_uncapped = x[3] == 1
        self.character.is_uncapped_override = x[4] == 1
        self.favorite_character = None if x[5] == - \
            1 else UserCharacter(self.c, x[5], self)

    def select_user_about_character(self) -> None:
        '''
            查询user表有关搭档的信息
        '''
        self.c.execute('''select name, character_id, is_skill_sealed, is_char_uncapped, is_char_uncapped_override, favorite_character from user where user_id = :a''', {
            'a': self.user_id})
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        self.from_list_about_character(x)

    def select_user_about_world_play(self) -> None:
        '''
            查询user表有关世界模式打歌的信息
        '''
        self.c.execute(
            '''select character_id, max_stamina_ts, stamina, is_skill_sealed, is_char_uncapped, is_char_uncapped_override, current_map, world_mode_locked_end_ts, beyond_boost_gauge, kanae_stored_prog from user where user_id=?''', (self.user_id,))
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        self.character = UserCharacter(self.c, x[0], self)
        self.stamina = UserStamina(self.c, self)
        self.stamina.set_value(x[1], x[2])
        self.is_skill_sealed = x[3] == 1
        self.character.is_uncapped = x[4] == 1
        self.character.is_uncapped_override = x[5] == 1
        self.current_map = UserMap(self.c, x[6], self)
        self.world_mode_locked_end_ts = x[7] if x[7] else -1
        self.beyond_boost_gauge = x[8] if x[8] else 0
        self.kanae_stored_prog = x[9] if x[9] else 0

    def select_user_about_link_play(self) -> None:
        '''
            查询 user 表有关 link play 的信息
        '''
        self.c.execute(
            '''select name, rating_ptt, is_hide_rating from user where user_id=?''', (self.user_id,))
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        self.name = x[0]
        self.rating_ptt = x[1]
        self.is_hide_rating = x[2] == 1

    @property
    def global_rank(self) -> int:
        '''用户潜力值排名，如果超过设定最大值，返回0'''
        if self.rating_ptt is None:
            self.select_user_one_column('rating_ptt', 0)
        if not self.rating_ptt:
            return 0

        self.c.execute(
            '''select count(*) from user where rating_ptt > ?''', (self.rating_ptt,))
        y = self.c.fetchone()
        if y and y[0] + 1 <= Config.WORLD_RANK_MAX:
            return y[0] + 1

        return 0

    def update_global_rank(self) -> None:
        '''用户世界排名计算，有新增成绩则要更新'''

        self.c.execute(
            '''
            with user_scores as (
            select song_id, difficulty, score_v2 from best_score where user_id = ? and difficulty in (2, 3, 4)
            )
            select sum(a) from(
            select sum(score_v2) as a from user_scores where difficulty = 2 and song_id in (select song_id from chart where rating_ftr > 0)
            union
            select sum(score_v2) as a from user_scores where difficulty = 3 and song_id in (select song_id from chart where rating_byn > 0)
            union
            select sum(score_v2) as a from user_scores where difficulty = 4 and song_id in (select song_id from chart where rating_etr > 0)
            )
            ''',
            (self.user_id,)
        )
        x = self.c.fetchone()
        if x[0] is None:
            return

        self.c.execute(
            '''update user set world_rank_score = ? where user_id = ?''', (x[0], self.user_id))
        self.world_rank_score = x[0]

    def update_user_world_complete_info(self) -> None:
        '''
            更新用户的世界模式完成信息，包括两个部分

            1. 每个章节的完成地图数量，为了 salt 技能
            2. 全世界模式完成台阶数之和，为了 fatalis 技能
        '''
        kvd = UserKVTable(self.c, self.user_id, 'world')

        for chapter_id, map_ids in MapParser.chapter_info_without_repeatable.items():
            self.c.execute(
                f'''select map_id, curr_position from user_world where user_id = ? and map_id in ({','.join(['?']*len(map_ids))})''',
                (self.user_id, *map_ids)
            )
            x = self.c.fetchall()
            n = 0
            for map_id, curr_position in x:
                step_count = MapParser.world_info[map_id]['step_count']
                if curr_position == step_count - 1:
                    n += 1
            kvd['chapter_complete_count', chapter_id] = n

        self.c.execute(
            '''select sum(curr_position) + count(*) from user_world where user_id = ?''', (self.user_id,)
        )
        x = self.c.fetchone()
        if x is not None:
            kvd['total_step_count'] = x[0] or 0

    def select_user_one_column(self, column_name: str, default_value=None, data_type=None) -> None:
        '''
            查询user表的某个属性
            请注意必须是一个普通属性，不能是一个类的实例
        '''
        if column_name not in self.__dict__:
            raise InputError('No such column.')
        self.c.execute(f'''select {column_name} from user where user_id = :a''', {
                       'a': self.user_id})
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)

        data = x[0] if x[0] is not None else default_value

        if data_type is not None:
            data = data_type(data)

        self.__dict__[column_name] = data

    def update_user_one_column(self, column_name: str, value=None) -> None:
        '''
            更新user表的某个属性
            请注意必须是一个普通属性，不能是一个类的实例
        '''
        if column_name not in self.__dict__:
            raise InputError('No such column.')
        if value is not None:
            self.__dict__[column_name] = value
        self.c.execute(f'''update user set {column_name} = :a where user_id = :b''', {
                       'a': self.__dict__[column_name], 'b': self.user_id})

    def change_profile(self, is_public: bool = None, custom_banner: str = None, showcase_characters: list = None) -> None:
        if is_public is not None:
            self.is_profile_public = is_public
            self.update_user_one_column('is_profile_public')
        if custom_banner is not None:
            self.custom_banner = custom_banner
            self.update_user_one_column('custom_banner')
        if showcase_characters is not None:
            self.update_user_one_column('showcase_characters', dumps(showcase_characters, separators=(',', ':')))
            self.showcase_characters = showcase_characters


class UserOnline(UserInfo):

    def __init__(self, c, user_id=None) -> None:
        super().__init__(c, user_id)

    def change_character(self, character_id: int, skill_sealed: bool = False):
        '''用户角色改变，包括技能封印的改变'''
        self.character = UserCharacter(self.c, character_id, self)
        self.character.select_character_uncap_condition()
        self.is_skill_sealed = skill_sealed

        self.c.execute('''update user set is_skill_sealed = :a, character_id = :b, is_char_uncapped = :c, is_char_uncapped_override = :d where user_id = :e''', {
            'a': 1 if self.is_skill_sealed else 0, 'b': self.character.character_id, 'c': self.character.is_uncapped, 'd': self.character.is_uncapped_override, 'e': self.user_id})

    def add_friend(self, friend_id: int):
        '''加好友'''
        if self.user_id == friend_id:
            raise FriendError('Add yourself as a friend.', 604)

        self.c.execute('''select exists(select * from friend where user_id_me = :x and user_id_other = :y)''',
                       {'x': self.user_id, 'y': friend_id})
        if self.c.fetchone() == (0,):
            self.c.execute('''insert into friend values(:a, :b)''', {
                           'a': self.user_id, 'b': friend_id})
        else:
            raise FriendError('The user has been your friend.', 602)

    def delete_friend(self, friend_id: int):
        '''删好友'''
        self.c.execute('''select exists(select * from friend where user_id_me = :x and user_id_other = :y)''',
                       {'x': self.user_id, 'y': friend_id})
        if self.c.fetchone() == (1,):
            self.c.execute('''delete from friend where user_id_me = :x and user_id_other = :y''',
                           {'x': self.user_id, 'y': friend_id})
        else:
            raise FriendError('No user or the user is not your friend.', 401)

    def change_favorite_character(self, character_id: int) -> None:
        '''更改用户的favorite_character'''
        self.favorite_character = UserCharacter(self.c, character_id, self)
        self.c.execute('''update user set favorite_character = :a where user_id = :b''',
                       {'a': self.favorite_character.character_id, 'b': self.user_id})

    def toggle_invasion(self) -> None:
        self.c.execute(
            '''select insight_state from user where user_id = ?''', (self.user_id,))
        x = self.c.fetchone()
        if not x:
            raise NoData('No user.', 108, -3)
        self.insight_state = x[0]
        rq = Constant.INSIGHT_TOGGLE_STATES
        self.insight_state = rq[(rq.index(self.insight_state) + 1) % len(rq)]

        self.c.execute(
            '''update user set insight_state = ? where user_id = ?''', (self.insight_state, self.user_id))


class UserChanger(UserInfo, UserRegister):

    def __init__(self, c, user_id=None) -> None:
        super().__init__(c, user_id)

    def update_columns(self, columns: list = None, d: dict = None) -> None:
        if columns is not None:
            d = {}
            for column in columns:
                if column == 'password' and self.password != '':
                    d[column] = self.hash_pwd
                else:
                    d[column] = self.__dict__[column]

        Sql(self.c).update('user', d, Query().from_args(
            {'user_id': self.user_id}))
