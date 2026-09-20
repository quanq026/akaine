from flask import Blueprint, current_app, request

from core.character import UserCharacter
from core.config_manager import Config
from core.error import ArcError
from core.item import ItemCore
from core.operation import DeleteOneUser
from core.save import SaveData
from core.sql import Connect
from core.user import User, UserLogin, UserOnline, UserRegister

from .auth import auth_required
from .func import arc_try, header_check, success_return

bp = Blueprint('user', __name__, url_prefix='/user')

bp2 = Blueprint('account', __name__, url_prefix='/account')

CLIENT_PACK_PROJECTION_APP_VERSION = '7.0.255'
CLIENT_PACK_PROJECTION_7_0_255 = (
    'base', 'extend_4', 'extend_3', 'extend_2', 'extend', 'konzetsu',
    'eclipse', 'lephon', 'epilogue', 'finale', 'vs', 'prelude', 'rei',
    'yugamu', 'core', 'nihil', 'eden', 'eden_append_1', 'eden_append_2',
    'megarex', 'anima', 'anima_append_1', 'observer', 'observer_append_1',
    'observer_append_2', 'dividedheart', 'alice', 'xd_fan_album',
    'omatsuri', 'zettai', 'nijuusei', 'nijuusei_append_1', 'mirai',
    'shiawase', 'djmax', 'djmax_append_1', 'rotaeno', 'cytusii',
    'cytusii_append_1', 'musedash', 'wacca', 'wacca_append_1', 'maimai',
    'maimai_append_1', 'maimai_append_2', 'ongeki', 'ongeki_append_1',
    'ongeki_append_2', 'chunithm', 'chunithm_append_1',
    'chunithm_append_2', 'chunithm_append_3', 'groovecoaster',
    'groovecoaster_append_1', 'tonesphere', 'lanota', 'lanota_append_1',
    'dynamix', 'virtualsingers', 'nextstage', 'undertale',
    'undertale_append_1',
)

CLIENT_UNLOCK_PROJECTION_7_0_255 = (
    'aegleseeker|0|103', 'aegleseeker|1|103', 'aegleseeker|2|103',
    'alterego|0|112', 'alterego|1|112', 'alterego|2|112', 'alterego|4|112',
    'arcanaeden|0|101', 'arcanaeden|0|104', 'arcanaeden|1|101',
    'arcanaeden|1|104', 'arcanaeden|2|101', 'arcanaeden|2|104',
    'arcanaeden|3|101', 'arcanaeden|3|104', 'arghena|0|103',
    'arghena|0|108', 'arghena|0|110', 'arghena|1|103', 'arghena|1|108',
    'arghena|1|110', 'arghena|2|103', 'arghena|2|108', 'arghena|2|110',
    'astralquant|0|101', 'astralquant|1|101', 'astralquant|2|101',
    'callimakarma|0|104', 'callimakarma|1|104', 'callimakarma|2|104',
    'deinosphainein|0|101', 'deinosphainein|1|101',
    'deinosphainein|2|101', 'deinosphainein|3|101', 'designant|0|101',
    'designant|1|101', 'designant|2|101', 'designant|3|101', 'ember|0|101',
    'ember|1|101', 'ember|2|101', 'fractureray|0|101', 'fractureray|1|101',
    'fractureray|2|101', 'grievouslady|0|101', 'grievouslady|1|101',
    'grievouslady|2|101', 'infinitestrife|0|101', 'infinitestrife|0|104',
    'infinitestrife|1|101', 'infinitestrife|1|104', 'infinitestrife|2|101',
    'infinitestrife|2|104', 'infinitestrife|3|101', 'infinitestrife|3|104',
    'lasteternity|0|104', 'lasteternity|1|104', 'lasteternity|2|104',
    'lasteternity|3|104', 'last|0|104', 'last|1|104', 'last|2|104',
    'last|3|104', 'lovelessdress|0|104', 'lovelessdress|1|104',
    'lovelessdress|2|104', 'pentiment|0|101', 'pentiment|0|104',
    'pentiment|1|101', 'pentiment|1|104', 'pentiment|2|101',
    'pentiment|2|104', 'pentiment|3|101', 'pentiment|3|104',
    'sacrosanct|0|101', 'sacrosanct|1|101', 'sacrosanct|2|101',
    'tempestissimo|0|101', 'tempestissimo|1|101', 'tempestissimo|2|101',
    'tempestissimo|3|101', 'testify|0|104', 'testify|1|104',
    'testify|2|104', 'testify|3|104', 'undyingmacula|0|101',
    'undyingmacula|1|101', 'undyingmacula|2|101', 'undyingmacula|4|101',
    'worldender|0|101', 'worldender|0|104', 'worldender|1|101',
    'worldender|1|104', 'worldender|2|101', 'worldender|2|104',
    'worldender|3|101', 'worldender|3|104',
)

CLIENT_UNLOCK_COMPLETE_BY_TYPE_7_0_255 = {
    '101': 999,
    '103': 999,
    '104': 1,
    '108': 1,
    '110': 999,
    '112': 999,
}

CLIENT_STORY_PROJECTION_7_0_255 = tuple(
    {'ma': 24, 'mi': index, 'c': True, 'r': True}
    for index in range(1, 11)
)


def replace_cloud_score_song_id(value, source, target):
    if isinstance(value, list):
        for item in value:
            replace_cloud_score_song_id(item, source, target)
    elif isinstance(value, dict):
        for key, item in value.items():
            if item == source:
                value[key] = target
            else:
                replace_cloud_score_song_id(item, source, target)


TESTIFY_CLOUD_FIELDS = (
    'scores_data',
    'clearlamps_data',
    'clearedsongs_data',
)
CLEAR_STATE = {3: 5, 2: 4, 5: 3, 1: 2, 4: 1, 0: 0}


def merge_testify_cloud_rows(rows, field):
    if not isinstance(rows, list):
        return rows
    result = []
    positions = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('song_id') != 'testify':
            result.append(row)
            continue
        key = row.get('difficulty')
        if key not in positions:
            positions[key] = len(result)
            result.append(row)
            continue
        current = result[positions[key]]
        if field == 'scores_data':
            old_rank = (current.get('score', 0), current.get('time_played', 0))
            new_rank = (row.get('score', 0), row.get('time_played', 0))
        elif field == 'clearlamps_data':
            old_rank = CLEAR_STATE.get(
                current.get('clear_type', current.get('ct', 0)), 0
            )
            new_rank = CLEAR_STATE.get(
                row.get('clear_type', row.get('ct', 0)), 0
            )
        else:
            old_rank = current.get('grade', 0)
            new_rank = row.get('grade', 0)
        if new_rank > old_rank:
            result[positions[key]] = row
    return result


def canonicalize_cloud_score_song_ids(save):
    for field in TESTIFY_CLOUD_FIELDS:
        replace_cloud_score_song_id(
            getattr(save, field), 'testify1', 'testify'
        )
        setattr(
            save,
            field,
            merge_testify_cloud_rows(getattr(save, field), field),
        )


def project_cloud_score_song_ids(save, app_version):
    canonicalize_cloud_score_song_ids(save)
    if app_version != CLIENT_PACK_PROJECTION_APP_VERSION:
        for field in TESTIFY_CLOUD_FIELDS:
            replace_cloud_score_song_id(
                getattr(save, field), 'testify', 'testify1'
            )


def client_pack_projection_for_app_version(app_version):
    if app_version == CLIENT_PACK_PROJECTION_APP_VERSION:
        return CLIENT_PACK_PROJECTION_7_0_255
    return None


def apply_client_unlock_projection(save, app_version):
    if (app_version != CLIENT_PACK_PROJECTION_APP_VERSION
            or not isinstance(save.unlocklist_data, list)):
        return
    projected = set(CLIENT_UNLOCK_PROJECTION_7_0_255)
    existing = set()
    for row in save.unlocklist_data:
        if isinstance(row, dict) and row.get('unlock_key') in projected:
            key = row['unlock_key']
            row['complete'] = CLIENT_UNLOCK_COMPLETE_BY_TYPE_7_0_255[
                key.rsplit('|', 1)[-1]
            ]
            existing.add(key)
    for key in projected - existing:
        save.unlocklist_data.append({
            'unlock_key': key,
            'complete': CLIENT_UNLOCK_COMPLETE_BY_TYPE_7_0_255[
                key.rsplit('|', 1)[-1]
            ],
        })


def apply_client_story_projection(save, app_version):
    if (app_version != CLIENT_PACK_PROJECTION_APP_VERSION
            or not isinstance(save.story_data, list)):
        return
    projected = {
        (row['ma'], row['mi']): row
        for row in CLIENT_STORY_PROJECTION_7_0_255
    }
    existing = set()
    for row in save.story_data:
        if isinstance(row, dict) and (row.get('ma'), row.get('mi')) in projected:
            key = row['ma'], row['mi']
            row.update(projected[key])
            existing.add(key)
    for projected in CLIENT_STORY_PROJECTION_7_0_255:
        key = projected['ma'], projected['mi']
        if key not in existing:
            save.story_data.append(dict(projected))


@bp.route('', methods=['POST'])  # 注册接口
@bp2.route('', methods=['POST'])
@arc_try
def register():
    error = header_check(request)
    if error is not None:
        raise error

    with Connect() as c:
        new_user = UserRegister(c)
        new_user.set_name(request.form['name'])
        new_user.set_password(request.form['password'])
        new_user.set_email(request.form['email'])
        if 'device_id' in request.form:
            device_id = request.form['device_id']
        else:
            device_id = 'low_version'

        ip = request.remote_addr
        new_user.register(device_id, ip)

        # 注册后自动登录
        user = UserLogin(c)
        user.login(new_user.name, new_user.password, device_id, ip)
        current_app.logger.info(f'New user `{user.user_id}` registered')
        return success_return({'user_id': user.user_id, 'access_token': user.token})


@bp.route('/me', methods=['GET'])  # 用户信息
@auth_required(request)
@arc_try
def user_me(user_id):
    with Connect() as c:
        app_version = request.headers.get('AppVersion')
        result = UserOnline(c, user_id).to_dict(
            client_pack_projection=client_pack_projection_for_app_version(
                app_version
            ),
            app_version=app_version,
        )
        if app_version == CLIENT_PACK_PROJECTION_APP_VERSION:
            result['packs'] = list(CLIENT_PACK_PROJECTION_7_0_255)
        return success_return(result)


@bp.route('/me/toggle_invasion', methods=['POST'])  # insight skill
@auth_required(request)
@arc_try
def toggle_invasion(user_id):
    with Connect() as c:
        user = UserOnline(c, user_id)
        user.toggle_invasion()
        return success_return({'user_id': user.user_id, 'insight_state': user.insight_state})


@bp.route('/me/character', methods=['POST'])  # 角色切换
@auth_required(request)
@arc_try
def character_change(user_id):
    with Connect() as c:
        user = UserOnline(c, user_id)
        user.change_character(
            int(request.form['character']), request.form['skill_sealed'] == 'true')

        return success_return({'user_id': user.user_id, 'character': user.character.character_id})


# 角色觉醒切换
@bp.route('/me/character/<int:character_id>/toggle_uncap', methods=['POST'])
@auth_required(request)
@arc_try
def toggle_uncap(user_id, character_id):
    with Connect() as c:
        user = User()
        user.user_id = user_id
        character = UserCharacter(c, character_id)
        character.change_uncap_override(user)
        character.select_character_info(user)
        return success_return({'user_id': user.user_id, 'character': [character.to_dict()]})


# 角色觉醒
@bp.route('/me/character/<int:character_id>/uncap', methods=['POST'])
@auth_required(request)
@arc_try
def character_first_uncap(user_id, character_id):
    with Connect() as c:
        user = UserOnline(c, user_id)
        character = UserCharacter(c, character_id)
        character.select_character_info(user)
        character.character_uncap(user)
        return success_return({'user_id': user.user_id, 'character': [character.to_dict()], 'cores': user.cores})


# 角色使用以太之滴
@bp.route('/me/character/<int:character_id>/exp', methods=['POST'])
@auth_required(request)
@arc_try
def character_exp(user_id, character_id):
    with Connect() as c:
        user = UserOnline(c, user_id)
        character = UserCharacter(c, character_id)
        character.select_character_info(user)
        core = ItemCore(c)
        core.amount = - int(request.form['amount'])
        core.item_id = 'core_generic'
        character.upgrade_by_core(user, core)
        return success_return({'user_id': user.user_id, 'character': [character.to_dict()], 'cores': user.cores})


@bp.route('/me/save', methods=['GET'])  # 从云端同步
@auth_required(request)
@arc_try
def cloud_get(user_id):
    with Connect() as c:
        app_version = request.headers.get('AppVersion')
        user = User()
        user.user_id = user_id
        save = SaveData(c)
        save.select_all(user)
        apply_client_unlock_projection(
            save, app_version
        )
        apply_client_story_projection(
            save, app_version
        )
        project_cloud_score_song_ids(save, app_version)
        return success_return(save.to_dict())


@bp.route('/me/save', methods=['POST'])  # 向云端同步
@auth_required(request)
@arc_try
def cloud_post(user_id):
    with Connect() as c:
        user = User()
        user.user_id = user_id
        save = SaveData(c)
        save.set_value(
            'scores_data', request.form['scores_data'], request.form['scores_checksum'])
        save.set_value(
            'clearlamps_data', request.form['clearlamps_data'], request.form['clearlamps_checksum'])
        save.set_value(
            'clearedsongs_data', request.form['clearedsongs_data'], request.form['clearedsongs_checksum'])
        save.set_value(
            'unlocklist_data', request.form['unlocklist_data'], request.form['unlocklist_checksum'])
        save.set_value(
            'installid_data', request.form['installid_data'], request.form['installid_checksum'])
        save.set_value('devicemodelname_data',
                       request.form['devicemodelname_data'], request.form['devicemodelname_checksum'])
        save.set_value(
            'story_data', request.form['story_data'], request.form['story_checksum'])
        save.set_value(
            'finalestate_data', request.form.get('finalestate_data'), request.form.get('finalestate_checksum'))

        canonicalize_cloud_score_song_ids(save)
        save.update_all(user)
        return success_return({'user_id': user.user_id})


@bp.route('/me/setting/<set_arg>', methods=['POST'])  # 三个设置
@auth_required(request)
@arc_try
def sys_set(user_id, set_arg):
    with Connect() as c:
        value = request.form['value']
        user = UserOnline(c, user_id)
        if 'favorite_character' == set_arg:
            user.change_favorite_character(int(value))
        else:
            value = 'true' == value
            if set_arg in ('is_hide_rating', 'max_stamina_notification_enabled', 'mp_notification_enabled'):
                user.update_user_one_column(set_arg, value)
        return success_return(user.to_dict(
            app_version=request.headers.get('AppVersion')
        ))


@bp.route('/me/profile', methods=['POST'])
@auth_required(request)
@arc_try
def user_profile(user_id):
    with Connect() as c:
        user = UserOnline(c, user_id)
        is_profile_public = request.form.get('is_profile_public')
        banner = request.form.get('banner')
        showcase_characters = None
        if any(k in request.form for k in ('sc_char_1', 'sc_char_2', 'sc_char_3')):
            showcase_characters = [
                request.form.get('sc_char_1', -1, type=int),
                request.form.get('sc_char_2', -1, type=int),
                request.form.get('sc_char_3', -1, type=int),
            ]
        user.select_user_about_profile()
        user.change_profile(None if is_profile_public is None else is_profile_public == 'true', banner, showcase_characters)
        return success_return({
            'is_profile_public': user.is_profile_public,
            'showcase_characters': user.showcase_characters,
            'world_unlock': '',
            'custom_banner': user.custom_banner,
        })


@bp.route('/me/request_delete', methods=['POST'])  # 删除账号
@bp2.route('/me/request_delete', methods=['POST'])
@auth_required(request)
@arc_try
def user_delete(user_id):
    if not Config.ALLOW_SELF_ACCOUNT_DELETE:
        raise ArcError('Cannot delete the account.', 151, status=404)
    DeleteOneUser().set_params(user_id).run()
    return success_return({'user_id': user_id})



@bp.route('/me/world_unlock', methods=['POST'])
@auth_required(request)
@arc_try
def world_unlock(user_id):
    current_app.logger.info(f"world_unlock: user_id={user_id}, form={dict(request.form)}")
    scenery = request.form.get('scenery') or request.form.get('item_id') or request.form.get('world_unlock')
    if scenery:
        with Connect() as c:
            c.execute('select exists(select * from user_item where user_id = ? and item_id = ? and type = ?)', (user_id, scenery, 'world_unlock'))
            if c.fetchone() == (0,):
                c.execute('select exists(select * from item where item_id = ? and type = ?)', (scenery, 'world_unlock'))
                if c.fetchone() == (0,):
                    c.execute('insert into item values(?,?,1)', (scenery, 'world_unlock'))
                c.execute('insert into user_item values(?,?,?,1)', (user_id, scenery, 'world_unlock'))
                current_app.logger.info(f"Successfully unlocked scenery/world_unlock {scenery} for user {user_id}")
    return success_return({})


@bp.route('/email/resend_verify', methods=['POST'])  # 邮箱验证重发
@bp2.route('/email/resend_verify', methods=['POST'])
@arc_try
def email_resend_verify():
    raise ArcError('Email verification unavailable.', 151, status=404)


@bp.route('/verify', methods=['POST'])  # 邮箱验证状态查询
@bp2.route('/verify', methods=['POST'])
@arc_try
def email_verify():
    raise ArcError('Email verification unavailable.', 151, status=404)
