struct DownloadPrompt {
    Address dialog = 0, button = 0;
};

bool download_pins() {
    for (const auto& pin : DOWNLOAD_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size))
            return false;
    return true;
}

DownloadPrompt download_prompt(Reader& reader,Address scene,const UiTree& tree,
                               const CliSongState& selection) {
    const Address dialog=tree.modal;
    if (!tree.valid || !tree.has_modal || tree.loading || !dialog || !download_pins() ||
        !selection.valid || selection.pack_open || selection.filter_open || !selection.selected ||
        !selection.song[0] || selection.difficulty!=selection.selected_difficulty ||
        !reader.readable(dialog,0x328) || reader.get<Address>(dialog)!=core+download_dialog_type ||
        !filter_widgets::member(tree,dialog,scene,true) || reader.get<uint8_t>(dialog+0x302) ||
        reader.get<uint8_t>(dialog+0x1c0)!=1)
        return {};
    unsigned difficulty=0;
    if (cli_song_in_list(reader,selection,selection.song,&difficulty)!=selection.selected
        || difficulty!=selection.selected_difficulty) return {};
    const Address root=reader.get<Address>(dialog+0x308),button=reader.get<Address>(dialog+0x320);
    if (!filter_widgets::member(tree,root,dialog,true) || !filter_widgets::member(tree,button,root,true) ||
        !ui_name(reader,button,"button1") || !filter_widgets::widget(reader,button,filter_button_type) ||
        reader.get<uint8_t>(button+0x448) || reader.get<Address>(button+0x398) ||
        reader.get<Address>(button+0x3a0) || reader.get<Address>(button+0x3a8) || reader.get<Address>(button+0x3d0))
        return {};
    const Address outer=reader.get<Address>(button+0x400);
    if (!reader.readable(outer,0x48) || reader.get<Address>(outer)!=core+download_outer_type ||
        reader.get<Address>(outer+0x10)!=dialog) return {};
    const Address inner=reader.get<Address>(outer+0x40);
    if (!reader.readable(inner,0x80) || reader.get<Address>(inner)!=core+download_inner_type ||
        reader.get<Address>(inner+0x30)!=scene ||
        !filter_widgets::pointer_pin(download_outer_type+0x30,download_outer_invoke) ||
        !filter_widgets::pointer_pin(download_inner_type+0x30,download_inner_invoke) ||
        !filter_widgets::pointer_pin(filter_button_type+0x630,entry_pack_release))
        return {};
    const Address begin=reader.get<Address>(inner+0x18),end=reader.get<Address>(inner+0x20);
    const Address cap=reader.get<Address>(inner+0x28),continuation=reader.get<Address>(inner+0x60);
    if (!reader.readable(begin,8) || end!=begin+8 || cap<end || cap-begin>256 ||
        reader.get<Address>(begin)!=selection.selected || !reader.readable(continuation,0x10) ||
        reader.get<Address>(continuation+8)!=scene)
        return {};
    const Address continuation_type=reader.get<Address>(continuation);
    const bool verified=(continuation_type==core+download_continuation_type &&
        filter_widgets::pointer_pin(download_continuation_type+0x30,download_continuation_invoke)) ||
        (continuation_type==core+download_refresh_type &&
        filter_widgets::pointer_pin(download_refresh_type+0x30,download_refresh_invoke));
    if (!verified || reader.fault)
        return {};
    return {dialog,button};
}

const char* activate_download(const DownloadPrompt& prompt) {
    if (!prompt.dialog || !prompt.button || !download_pins()) return "DOWNLOAD_PROMPT_UNAVAILABLE";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host;
    host.call<void>(entry_pack_release,prompt.button);
    return host.fault?"NATIVE_GUARD":nullptr;
}
