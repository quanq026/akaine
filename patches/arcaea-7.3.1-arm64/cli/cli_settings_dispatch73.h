#include "settings_controls73.h"
#include "settings_panel73.h"

int pending_setting=0;

bool settings_confirmed(const char* action,const settings_panel_cli::View& panel,
                        const settings_cli::View& preference,int expected) {
    if (!panel.available || panel.blocked || panel.reason) return false;
    if (!strcmp(action,"open")) return panel.panel && panel.close_button && preference.panel_open;
    if (!strcmp(action,"close")) return !panel.panel && panel.open_button && !preference.panel_open;
    if (!panel.panel || !preference.available || !preference.panel_open) return false;
    if (!strncmp(action,"fps:",4))
        return panel.high_framerate.node && panel.high_framerate.current==expected &&
               preference.high_framerate==expected;
    if (!strncmp(action,"speed:",6))
        return panel.note_speed.node && panel.note_speed.current==expected &&
               preference.highspeed_int==expected;
    return !strncmp(action,"offset:",7) && panel.offset.node && panel.offset.current==expected &&
        (preference.audio_preset?preference.offset_bluetooth:preference.offset_normal)==expected;
}

const char* settings_action(const char* action,Reader& reader,const settings_panel_cli::View& panel,
                             const settings_cli::View& preference,int value) {
    if (!strcmp(action,"open")) return settings_panel_cli::open(reader,panel);
    if (!strcmp(action,"close")) return settings_panel_cli::close(reader,panel);
    if (!strncmp(action,"fps:",4))
        return settings_panel_cli::set_fps(reader,panel,value,preference.available?preference.high_framerate:-1);
    if (!strncmp(action,"speed:",6)) return settings_panel_cli::set_speed(reader,panel,value);
    if (!strncmp(action,"offset:",7)) return settings_panel_cli::set_offset(reader,panel,value);
    return "INVALID_ARGUMENT";
}
