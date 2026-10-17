"""Pure-Python H3 binding formatter; no model loading or network access."""

import json

import re

PICTURE_ROLES = ("face", "hair", "outfit", "body", "appearance", "setting", "start frame", "object",
                 "face sheet", "character sheet")

VIDEO_ROLES = ("body motion", "motion", "full motion", "mouth", "pose", "depth",
               "likeness", "edit source", "setting")

_VIDEO_LIKENESS_ALIASES = {"likeness", "appearance", "face", "identity", "look",
                           "looks", "character", "person", "subject"}

AUDIO_ROLES = ("soundtrack", "lipsync", "voice", "music", "bed", "offscreen voice")

_SUBJECT_ROLES = {"face", "hair", "outfit", "body", "appearance",
                  "face sheet", "character sheet",
                  "body motion", "mouth", "pose", "depth", "likeness", "lipsync"}

_SUBJ_LINE = re.compile(r"^subject\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)

_REF_LINE = re.compile(r"^(picture|pic|video|vid|audio|aud)\s+([a-z0-9]+)\s*:\s*(.+)$", re.IGNORECASE)

_SETTING_LINE = re.compile(r"^setting\s*:\s*(.+)$", re.IGNORECASE)

_SETTING_MODE_LINE = re.compile(r"^setting\s+mode\s*:\s*(subject|picture)\s*$",
                                re.IGNORECASE)

_SOUNDSCAPE_LINE = re.compile(r"^soundscape\s*:\s*(.+)$", re.IGNORECASE)

_APPEND_LINE = re.compile(r"^append\s+(all|init|loop)\s*:\s*(.+)$", re.IGNORECASE)

_PREFIX_LINE = re.compile(r"^summary\s+prefixes?\s+(init|loop)\s*:\s*(.+)$", re.IGNORECASE)

_LOOPTAIL_LINE = re.compile(
    r"^loop[\s_]*tail\s*:\s*(latent[\s_]*anchor|video[\s_]*ref|anchor|ref)\s*$",
    re.IGNORECASE)

_NOTE = re.compile(r"\(([^)]*)\)\s*$")

LOOP_TAIL_DEFAULT = "latent_anchor"

class DSLError(ValueError):
    pass

_ROLE_ALIASES = {"motion": "body motion", "full motion": "body motion",
                 "source": "edit source", "source video": "edit source",
                 "edit": "edit source", "editing source": "edit source",
                 "edit-source": "edit source",
                 "startframe": "start frame", "start_frame": "start frame",
                 "first frame": "start frame", "background": "setting",
                 "scene": "setting", "environment": "setting",
                 "clothes": "outfit", "clothing": "outfit", "wardrobe": "outfit",
                 "build": "body", "body type": "body", "body shape": "body",
                 "physique": "body", "figure": "body",
                 "voice": "lipsync", "audio": "soundtrack",
                 "ambience": "bed", "ambient": "bed", "background bed": "bed",
                 "narrator": "offscreen voice", "off-screen voice": "offscreen voice",
                 "off screen voice": "offscreen voice", "offscreen": "offscreen voice",
                 "background music": "music", "bgm": "music", "score": "music",
                 "lips": "mouth", "tongue": "mouth",
                 "sheet": "character sheet", "char sheet": "character sheet",
                 "charsheet": "character sheet", "character-sheet": "character sheet",
                 "facesheet": "face sheet", "face-sheet": "face sheet",
                 "faces sheet": "face sheet"}

def _norm_role(name):
    name = re.sub(r"\s+", " ", name.strip().lower())
    return _ROLE_ALIASES.get(name, name)

_SUBJECT_TOKEN = re.compile(r"^(?:subject\s*|s)?(\d+)$|^(?:all|both|everyone)$",
                            re.IGNORECASE)

def _parse_targets(s, line_no):
    s = s.strip().lower()
    if s in ("all", "both", "everyone"):
        return "all"
    out = []
    for part in re.split(r"[,+&]| and ", s):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(?:subject\s*|s)?(\d+)$", part)
        if not m:
            raise DSLError(
                f"line {line_no}: cannot parse subject target '{part}' — "
                f"targets are '1', 'subject 2', or 'all', and ROLES are "
                f"separated by ';' (e.g. 'face -> 1,2; setting; start frame')")
        out.append(int(m.group(1)))
    if not out:
        raise DSLError(f"line {line_no}: empty subject target list")
    return out

def _parse_roles(text, kind, line_no):
    """'face -> 1,2 (primary); setting; start frame' -> [role dicts].

    Forgiving about separators: ';' and ',' both work between roles, and
    role names typed into a target list ('face -> 1,2, setting, start
    frame') are peeled off as additional roles instead of erroring."""
    valid = {"picture": PICTURE_ROLES, "video": VIDEO_ROLES, "audio": AUDIO_ROLES}[kind]
    roles = []

    def _flush(name, target_parts, note):
        name = _norm_role(name)
        if kind == "video" and name in _VIDEO_LIKENESS_ALIASES:
            name = "likeness"
        if name not in valid:
            raise DSLError(
                f"line {line_no}: unknown {kind} role '{name}' "
                f"(valid: {', '.join(valid)})")
        targets = _parse_targets(", ".join(target_parts), line_no) if target_parts else []
        roles.append({"role": name, "targets": targets, "note": note})

    for raw in text.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        seg_start = len(roles)
        arrow_name, pending, note = None, [], None
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            tok_note = None
            m = _NOTE.search(tok)
            if m:
                tok_note = m.group(1).strip()
                tok = tok[: m.start()].strip()
            if "->" in tok:
                if arrow_name is not None:
                    _flush(arrow_name, pending, note)
                name, _, t0 = tok.partition("->")
                arrow_name, note = name, tok_note
                pending = [t0.strip()] if t0.strip() else []
            elif arrow_name is not None and _SUBJECT_TOKEN.match(tok):
                pending.append(tok)
                if tok_note:
                    note = tok_note
            else:
                if arrow_name is not None:
                    _flush(arrow_name, pending, note)
                    arrow_name, pending, note = None, [], None
                if tok:
                    _flush(tok, [], tok_note)
        if arrow_name is not None:
            _flush(arrow_name, pending, note)
        # Backfill: in 'hair, outfit -> 1' the roles typed before the arrow
        # share the arrow's targets instead of silently binding to nobody.
        seg = roles[seg_start:]
        for j, r in enumerate(seg):
            if not r["targets"] and r["role"] in _SUBJECT_ROLES:
                nxt = next((s["targets"] for s in seg[j + 1:] if s["targets"]), None)
                if nxt:
                    r["targets"] = list(nxt)
    if not roles:
        raise DSLError(f"line {line_no}: no roles declared")
    return roles

def parse_bindings(dsl_text):
    """Parse the DSL into a bindings dict. Raises DSLError with line numbers."""
    b = {"subjects": {}, "pictures": [], "videos": [], "audios": [],
         "setting": None, "setting_mode": "picture", "soundscape": None,
         "appends": {"all": [], "init": [], "loop": []},
         "summary_prefixes": {"init": None, "loop": None},
         "loop_tail": LOOP_TAIL_DEFAULT}
    for i, raw in enumerate(dsl_text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _SUBJ_LINE.match(line)
        if m:
            n = int(m.group(1))
            rest = m.group(2)
            # 'lora:' first — the position regex is end-anchored and would
            # otherwise swallow a trailing '; lora: token'.
            lora = None
            lm = re.search(r"[|;]\s*lora\s*:\s*([^|;]*)", rest, re.IGNORECASE)
            if lm:
                lora = lm.group(1).strip().rstrip(".")
                if not lora:
                    raise DSLError(f"line {i}: empty lora token "
                                   "(expected e.g. '; lora: emie')")
                rest = (rest[: lm.start()] + rest[lm.end():]).strip()
            position = None
            pm = re.search(r"[|;]\s*position\s*:\s*(.+)$", rest, re.IGNORECASE)
            if pm:
                position = pm.group(1).strip().rstrip(".")
                rest = rest[: pm.start()].strip()
            b["subjects"][n] = {"desc": rest.strip().rstrip("."),
                                "position": position, "lora": lora}
            continue
        m = _REF_LINE.match(line)
        if m:
            kind = {"pic": "picture", "vid": "video", "aud": "audio"}.get(
                m.group(1).lower()[:3], m.group(1).lower())
            key = m.group(2).upper()
            roles = _parse_roles(m.group(3), kind, i)
            b[{"picture": "pictures", "video": "videos", "audio": "audios"}[kind]].append(
                {"id": key, "roles": roles})
            continue
        m = _SETTING_MODE_LINE.match(line)
        if m:
            b["setting_mode"] = m.group(1).lower()
            continue
        m = _SETTING_LINE.match(line)
        if m:
            b["setting"] = m.group(1).strip().rstrip(".")
            continue
        m = _SOUNDSCAPE_LINE.match(line)
        if m:
            b["soundscape"] = m.group(1).strip()
            continue
        m = _APPEND_LINE.match(line)
        if m:
            b["appends"][m.group(1).lower()].append(m.group(2).strip())
            continue
        m = _PREFIX_LINE.match(line)
        if m:
            b["summary_prefixes"][m.group(1).lower()] = m.group(2).strip()
            continue
        m = _LOOPTAIL_LINE.match(line)
        if m:
            v = re.sub(r"[\s_]+", "", m.group(1).lower())
            b["loop_tail"] = "video_ref" if v in ("videoref", "ref") else "latent_anchor"
            continue
        raise DSLError(f"line {i}: cannot parse '{line}'")

    if not b["subjects"]:
        raise DSLError("no subjects declared (need at least 'subject 1: ...')")
    # Validate targets exist
    subj_ids = set(b["subjects"])
    for group in ("pictures", "videos", "audios"):
        for ref in b[group]:
            for role in ref["roles"]:
                if role["targets"] == "all":
                    role["targets"] = sorted(subj_ids)
                elif not role["targets"] and role["role"] in _SUBJECT_ROLES:
                    role["targets"] = sorted(subj_ids)
                for t in role["targets"]:
                    if t not in subj_ids:
                        raise DSLError(f"{group[:-1]} {ref['id']}: role "
                                       f"'{role['role']}' targets undeclared subject {t}")

    # Character-sheet expansion. A 'face sheet' is a multi-view face source; a
    # 'character sheet' fills every attribute slot (face/hair/outfit/appearance)
    # that no explicit picture already covers for its subjects, so granular
    # declarations always win over the sheet.
    explicit = set()
    for ref in b["pictures"]:
        for role in ref["roles"]:
            rn = role["role"]
            if rn in ("face", "hair", "outfit", "body", "appearance"):
                base = "appearance" if rn in ("body", "appearance") else rn
                for t in role["targets"]:
                    explicit.add((base, t))
    for ref in b["pictures"]:
        expanded = []
        for role in ref["roles"]:
            if role["role"] == "face sheet":
                ref["sheet"] = "face"
                ref["sheet_targets"] = list(role["targets"])
                expanded.append({"role": "face", "targets": role["targets"],
                                 "note": role["note"]})
            elif role["role"] == "character sheet":
                ref["sheet"] = "full"
                ref["sheet_targets"] = list(role["targets"])
                added = False
                for rn in ("face", "hair", "outfit", "appearance"):
                    targets = [t for t in role["targets"]
                               if (rn, t) not in explicit]
                    if targets:
                        expanded.append({"role": rn, "targets": targets,
                                         "note": role["note"]})
                        added = True
                if not added:  # everything covered explicitly: reinforce appearance
                    expanded.append({"role": "appearance",
                                     "targets": list(role["targets"]),
                                     "note": role["note"]})
            else:
                expanded.append(role)
        ref["roles"] = expanded
    return b

def _strip_article(text):
    return re.sub(r"^(?:a|an|the)\s+", "", text.strip(), flags=re.IGNORECASE)

def _or_join(tags):
    tags = list(tags)
    if len(tags) <= 1:
        return tags[0] if tags else ""
    if len(tags) == 2:
        return f"{tags[0]} or {tags[1]}"
    return ", ".join(tags[:-1]) + ", or " + tags[-1]

def _pron(desc):
    d = desc.lower()
    if re.search(r"\b(woman|girl|lady|female|she)\b", d):
        return "Her"
    if re.search(r"\b(man|guy|male|boy|he)\b", d):
        return "His"
    return "Their"

def _stag(n):
    return f"<Subject {n}>"

def _join(tags):
    tags = list(tags)
    if len(tags) <= 1:
        return tags[0] if tags else ""
    return ", ".join(tags[:-1]) + " and " + tags[-1]

def _poss_join(subject_ns):
    """[1] -> "<Subject 1>'s", [1,2] -> "<Subject 1>'s and <Subject 2>'s" """
    return _join([f"{_stag(n)}'s" for n in subject_ns])

def _pic_roles_for(b, subject_n, role_name):
    """Pictures (in declaration order) holding role_name for subject_n."""
    out = []
    for ref in b["pictures"]:
        for role in ref["roles"]:
            if role["role"] == role_name and subject_n in role["targets"]:
                out.append((ref, role))
    return out

def _vid_roles_for(b, subject_n, role_name):
    """Videos (in declaration order) holding role_name for subject_n."""
    out = []
    for ref in b["videos"]:
        for role in ref["roles"]:
            if role["role"] == role_name and subject_n in role["targets"]:
                out.append((ref, role))
    return out

def compile_phase(b, phase):
    """Compile bindings for 'init' or 'loop'. Returns dict of section texts +
    substitution map + guidance."""
    loop = phase == "loop"
    # video_ref: legacy loop graphs carry the tail as ref_video_0, so <Video 1>
    # / <Audio 1> are reserved for it and declared refs shift up by one.
    # latent_anchor (default): the tail rides latent-anchor nodes, refs number
    # from 1 in every phase and no tail lines are emitted.
    tail_ref = loop and b.get("loop_tail", LOOP_TAIL_DEFAULT) == "video_ref"

    pic_num = {ref["id"]: ref["id"] for ref in b["pictures"]}  # literal numbers
    # latent_anchor (default): emit DECLARED slot numbers for videos/audios too,
    # exactly like pictures, so the sampler-side H3TagRenumber can compact them
    # to the live wire. A gap (e.g. video slot 1 unused, 2/3 active) MUST survive
    # into the file — pre-compacting here to 1..N shifts the tags down and then
    # the wire-side renumber compacts a second time, so a gated-off slot 1 makes
    # the file's <Video 1> reference an inactive slot and validation errors.
    # video_ref mode instead reserves <Video 1>/<Audio 1> for the carried tail
    # and turns the downstream renumber OFF, so there it needs the final compacted
    # numbers (declared refs shift up past the tail).
    def _literal_slot(key):
        # Declared ids are digits ('video 2') or Ctrl-slot letters ('video B'
        # = Ctrl B = slot 2); tags always render numerically (<Video 2>).
        if key.isdigit():
            return int(key)
        if len(key) == 1 and key.isalpha():
            return ord(key) - ord("A") + 1
        return key

    vid_num = {}
    aud_num = {}
    if tail_ref:
        for i, ref in enumerate(b["videos"]):
            vid_num[ref["id"]] = 2 + i
        for i, ref in enumerate(b["audios"]):
            aud_num[ref["id"]] = 2 + i
    else:
        for ref in b["videos"]:
            vid_num[ref["id"]] = _literal_slot(ref["id"])
        for ref in b["audios"]:
            aud_num[ref["id"]] = _literal_slot(ref["id"])

    def ptag(ref):
        return f"<Picture {pic_num[ref['id']]}>"

    def vtag(ref):
        return f"<Video {vid_num[ref['id']]}>"

    def atag(ref):
        return f"<Audio {aud_num[ref['id']]}>"

    subjects = sorted(b["subjects"])
    sd_lines = []

    # Whole-video relationships (official guide §2.3): 'edit source' marks the
    # video the target is an edited version of; 'setting' keeps the video's own
    # environment as the target's setting.
    edit_vids = [ref for ref in b["videos"]
                 if any(r["role"] == "edit source" for r in ref["roles"])]
    scene_vids = [ref for ref in b["videos"]
                  if any(r["role"] == "setting" for r in ref["roles"])]
    likeness_vids = [ref for ref in b["videos"]
                     if any(r["role"] == "likeness" for r in ref["roles"])]

    def _role_note(ref, role_name):
        return next((r["note"] for r in ref["roles"]
                     if r["role"] == role_name and r["note"]), None)

    if tail_ref:
        sd_lines.append("<Video 1> is the tail of the footage this video "
                        "continues; the target video extends it seamlessly.")
        if b["audios"]:
            sd_lines.append("<Audio 1> is the soundtrack carried over from that footage.")

    # Subject definitions
    for n in subjects:
        s = b["subjects"][n]
        pron = _pron(s["desc"])
        parts = [f"{_stag(n)} is {s['desc']}."]
        faces = _pic_roles_for(b, n, "face")
        if faces:
            prim = next((f for f in faces if f[1]["note"] and "primary" in f[1]["note"].lower()), faces[0])
            rest = [f for f in faces if f is not prim]
            line = f"{pron} face comes exactly from {ptag(prim[0])}"
            if rest:
                tags = _join([ptag(r[0]) for r in rest])
                angle = ("shows the same face from another angle"
                         if len(rest) == 1
                         else "show the same face from other angles")
                line += f", and {tags} {angle} as reinforcement"
            parts.append(line + ".")
        hairs = _pic_roles_for(b, n, "hair")
        if hairs:
            frags = [ptag(r) + (f" ({role['note']})" if role["note"] else "")
                     for r, role in hairs]
            parts.append(f"{pron} hairstyle comes from {_join(frags)}.")
        outfits = _pic_roles_for(b, n, "outfit")
        if outfits:
            frags = [ptag(r) + (f" ({role['note']})" if role["note"] else "")
                     for r, role in outfits]
            parts.append(f"{pron} outfit comes from {_join(frags)}.")
        # 'body' = build/proportions only (an attribute like hair/outfit);
        # 'appearance' = the whole look minus the face.
        bodies = _pic_roles_for(b, n, "body")
        if bodies:
            frags = [ptag(r) + (f" ({role['note']})" if role["note"] else "")
                     for r, role in bodies]
            parts.append(f"{pron} body type and build come from {_join(frags)}.")
        looks = _pic_roles_for(b, n, "appearance")
        if looks:
            frags = [ptag(r) for r, _ in looks]
            parts.append(f"{pron} overall appearance comes from {_join(frags)}.")
        subj_pron = {"Her": "She", "His": "He", "Their": "They"}[pron]
        from_pics = bool(faces or hairs or outfits or bodies or looks)
        # Likeness VIDEO(s): the subject is the person in the clip (guide 2.1
        # '<Subject N> is the woman in <Video 1>'). Pictures win where they
        # bind; the clip fills the rest - the same precedence as the LoRA mix.
        likes = _vid_roles_for(b, n, "likeness")
        plain_tags = ""
        if likes:
            like_tags = _join([vtag(r) + (f" ({role['note']})" if role["note"] else "")
                               for r, role in likes])
            plain_tags = _join([vtag(r) for r, _ in likes])
            if from_pics:
                verb = "reinforce" if len(likes) > 1 else "reinforces"
                parts.append(f"{subj_pron} is also the person shown in {like_tags}; "
                             f"{plain_tags} {verb} {pron.lower()} appearance in "
                             "every detail not covered by the reference pictures.")
            else:
                parts.append(f"{subj_pron} is the person shown in {like_tags}; "
                             f"{pron.lower()} face, hair, and overall appearance "
                             f"come exactly from {plain_tags}.")
        token = s.get("lora")
        if token:
            if from_pics or likes:
                # Contradictory-but-allowed mix: pictures/clips win where they
                # bind, the LoRA identity fills everything else.
                covered = ((["the reference pictures"] if from_pics else [])
                           + ([plain_tags] if likes else []))
                parts.append(f"{_stag(n)} is {token} in every detail not "
                             f"covered by {_join(covered)}.")
            else:
                parts.append(f"{subj_pron} does not appear in any reference "
                             f"picture; {subj_pron.lower()} is {token}.")
        sd_lines.append(" ".join(parts))

    # Character-sheet acknowledgments
    for ref in b["pictures"]:
        sheet = ref.get("sheet")
        if not sheet:
            continue
        tgt = _join([_stag(n) for n in ref.get("sheet_targets", [])])
        if sheet == "face":
            sd_lines.append(f"{ptag(ref)} is a character sheet of {tgt}: every "
                            "panel shows the same face from a different angle.")
        else:
            sd_lines.append(f"{ptag(ref)} is a full character sheet of {tgt}: "
                            "all panels show the same person.")

    # Position bindings inside a shared reference image
    multi_face_pics = [ref for ref in b["pictures"]
                       if len({t for role in ref["roles"] if role["role"] == "face"
                               for t in role["targets"]}) >= 2]
    positioned = [n for n in subjects if b["subjects"][n]["position"]]
    if multi_face_pics and len(positioned) >= 2:
        ref = multi_face_pics[0]
        clauses = _join([f"{b['subjects'][n]['position']} is {_stag(n)}"
                         for n in positioned])
        sd_lines.append(f"In {ptag(ref)}, {clauses}.")

    # Setting. 'picture' mode (legacy default) hangs the setting text on a
    # standalone <Picture N> line. 'subject' mode follows the official guide
    # §2.2: the ENVIRONMENT becomes its own <Subject K> (next free number,
    # compiled-text only — never added to b['subjects'], so emotion schedules,
    # speech locks, and role targets are untouched) that cites the picture
    # inline; retention and the summary then reference the subject tag.
    setting_pics = [ref for ref in b["pictures"]
                    if any(role["role"] == "setting" for role in ref["roles"])]
    env_subject_n = None
    if setting_pics and b.get("setting_mode", "picture") == "subject":
        env_subject_n = max(int(n) for n in subjects) + 1
    if setting_pics:
        stext = b["setting"] or "the environment shown"
        if env_subject_n:
            if b["setting"]:
                sd_lines.append(f"{_stag(env_subject_n)} is {stext}, the "
                                f"environment shown in {ptag(setting_pics[0])}.")
            else:
                sd_lines.append(f"{_stag(env_subject_n)} is the environment "
                                f"shown in {ptag(setting_pics[0])}.")
        else:
            sd_lines.append(f"{ptag(setting_pics[0])} defines the setting: {stext}.")
    if scene_vids:
        stext = b["setting"] or "the environment shown"
        snote = _role_note(scene_vids[0], "setting")
        sd_lines.append(f"{vtag(scene_vids[0])} defines the setting: {stext}; "
                        "the target video keeps this environment throughout"
                        + (f"; {snote}." if snote else "."))
    if not setting_pics and not scene_vids and b["setting"]:
        sd_lines.append(f"The setting is {b['setting']}.")

    # Start frame (init only)
    start_pics = [ref for ref in b["pictures"]
                  if any(role["role"] == "start frame" for role in ref["roles"])]
    if start_pics and not loop:
        sd_lines.append(f"{ptag(start_pics[0])} is the exact first frame of the video.")

    # Video roles
    def _video_group(role_name, verb_phrase):
        groups = {}
        for ref in b["videos"]:
            for role in ref["roles"]:
                if role["role"] == role_name:
                    groups.setdefault(tuple(role["targets"]), []).append(ref)
        lines = []
        for targets, refs in groups.items():
            tags = _join([vtag(r) for r in refs])
            verb = "provide" if len(refs) > 1 else "provides"
            lines.append(f"{tags} {verb} {_poss_join(list(targets))} {verb_phrase}.")
        return lines

    for ref in edit_vids:
        note = _role_note(ref, "edit source")
        line = f"{vtag(ref)} is the source video for the target video edit"
        sd_lines.append(line + (f"; {note}." if note else "."))

    sd_lines += _video_group("body motion", "body motions and actions")
    sd_lines += _video_group("mouth", "mouth, lip, and tongue movements")
    sd_lines += _video_group("pose", "poses")
    sd_lines += _video_group("depth", "spatial arrangement")

    # Motion position mapping (which performer drives which subject)
    motion_refs = [ref for ref in b["videos"]
                   if any(role["role"] == "body motion" and len(role["targets"]) >= 2
                          for role in ref["roles"])]
    if motion_refs and len(positioned) >= 2:
        tags = _join([vtag(r) for r in motion_refs])
        clauses = _join([f"{b['subjects'][n]['position']} performs {_stag(n)}'s motions"
                         for n in positioned])
        sd_lines.append(f"In {tags}, {clauses}.")

    # Voice ownership and face visibility are separate, per-utterance facts.
    def _vocal_verb(lp):
        if lp["note"]:
            return lp["note"].strip()
        return "speak" if len(lp["targets"]) > 1 else "speaks"

    for ref in b["audios"]:
        roles = {role["role"]: role for role in ref["roles"]}
        lp = roles.get("lipsync")
        has_music = "music" in roles
        vw = "voices" if lp and len(lp["targets"]) > 1 else "voice"
        if "bed" in roles and not lp:
            if "offscreen voice" in roles:
                sd_lines.append(f"{atag(ref)} is the background soundtrack of "
                                "the target video: ambience, music, and an "
                                "OFF-SCREEN speaker's voice. That off-screen "
                                "voice belongs to no visible subject and no "
                                "one on screen speaks or mouths it; every "
                                "visible subject's spoken voice is newly "
                                "generated and is not present in this audio.")
            else:
                sd_lines.append(f"{atag(ref)} is the background soundtrack of the "
                                "target video: ambience and music only — every "
                                "spoken voice heard in the target video is newly "
                                "generated and is not present in this audio.")
        elif "soundtrack" in roles and lp:
            tgt = _join([_stag(n) for n in lp["targets"]])
            line = (f"{atag(ref)} is the complete soundtrack of the target "
                    f"video, including dialogue attributed to {tgt} and any off-screen voices")
            sd_lines.append(line + (", over background music." if has_music else "."))
        elif lp:
            tgt = _join([_stag(n) for n in lp["targets"]])
            sd_lines.append(f"{atag(ref)} supplies {tgt}'s {vw}; each utterance's "
                            "visibility is specified in the description.")
        elif "soundtrack" in roles or has_music:
            what = "background music" if has_music else "background audio"
            sd_lines.append(f"{atag(ref)} is the soundtrack of the target video: "
                            f"{what}; no one on screen performs it.")

    subject_definitions = "\n".join(sd_lines)

    # ---- summary ----
    prefix = b["summary_prefixes"]["loop" if loop else "init"]
    if not prefix:
        parts = []
        if edit_vids:
            parts.append("video editing")
        if loop:
            # official task-type vocabulary: 'video continuation' (the
            # once-used 'video extension' is out-of-vocabulary, guide §3)
            parts.append("video continuation")
        if b["pictures"] or likeness_vids:
            parts.append("reference generation")
        if start_pics and not loop:
            parts.append("keyframe completion")
        if b["audios"]:
            parts.append("audio reuse")
        prefix = "[" + " + ".join(parts) + "]"

    subj_clauses = []
    for n in subjects:
        clause = _stag(n)
        srcs = []
        faces = _pic_roles_for(b, n, "face")
        if faces:
            srcs.append(f"the face of {ptag(faces[0][0])}")
        hairs = _pic_roles_for(b, n, "hair")
        if hairs:
            srcs.append(f"the hairstyle and hair color of {ptag(hairs[0][0])}")
        outfits = _pic_roles_for(b, n, "outfit")
        if outfits:
            srcs.append(f"the clothing of {ptag(outfits[0][0])}")
        bodies = _pic_roles_for(b, n, "body")
        if bodies:
            srcs.append(f"the body type and build of {ptag(bodies[0][0])}")
        looks = _pic_roles_for(b, n, "appearance")
        if looks:
            srcs.append(f"the overall appearance of {ptag(looks[0][0])}")
        likes = _vid_roles_for(b, n, "likeness")
        if likes:
            what = "the appearance of" if srcs else "the identity and appearance of"
            srcs.append(f"{what} {_join([vtag(r) for r, _ in likes])}")
        if srcs:
            clause += " with " + _join(srcs)
        elif b["subjects"][n].get("lora"):
            clause += f" as {b['subjects'][n]['lora']}"
        subj_clauses.append(clause)

    motion_tags = [vtag(r) for r in b["videos"]
                   if any(role["role"] == "body motion" for role in r["roles"])]
    mouth_tags = [vtag(r) for r in b["videos"]
                  if any(role["role"] == "mouth" for role in r["roles"])]
    motion_clause = ""
    if motion_tags:
        motion_clause = f"performing the body motions of {_join(motion_tags)}"
    if mouth_tags:
        motion_clause += (" and " if motion_clause else "") + \
            f"the mouth movements of {_join(mouth_tags)}"
    aud_sound = [atag(r) for r in b["audios"]
                 if any(role["role"] == "soundtrack" for role in r["roles"])]
    if aud_sound and motion_clause:
        motion_clause += f" in sync with {aud_sound[0]}"

    setting_clause = ""
    if setting_pics and env_subject_n:
        setting_clause = f"in {_stag(env_subject_n)}"
    elif setting_pics:
        setting_clause = f"in the setting of {ptag(setting_pics[0])}"
    elif scene_vids:
        setting_clause = f"in the preserved setting of {vtag(scene_vids[0])}"
    elif b["setting"]:
        setting_clause = f"in {b['setting']}"

    if loop:
        src = "the footage of <Video 1>" if tail_ref else "the ongoing footage"
        body = f"Continue {src} seamlessly: {_join(subj_clauses)}"
        body += f" {'continue' if len(subjects) > 1 else 'continues'} " \
            + (motion_clause or "the ongoing action")
    else:
        body = f"Generate {_join(subj_clauses)}"
        if motion_clause:
            body += ", " + motion_clause
    if setting_clause:
        body += ", " + setting_clause
    if start_pics and not loop:
        body += f", starting exactly from the frame of {ptag(start_pics[0])}"
    # Official guide: video-editing summaries begin with this exact sentence
    # right after the task-type prefix.
    edit_intro = (f"The target video is an edited version of "
                  f"{vtag(edit_vids[0])}. " if edit_vids else "")
    summary = f"{prefix} {edit_intro}{body}."

    # ---- retention_analysis ----
    ra_lines = []
    if tail_ref:
        ra_lines.append("<Video 1> (existing footage): fully_preserved - the "
                        "opening moments are existing footage, preserved exactly; "
                        "the continuation keeps its scene, framing, camera, and "
                        "lighting; it is never an appearance source.")
        if b["audios"]:
            ra_lines.append("<Audio 1> (carried audio): partially_copy - preserved "
                            "over the opening footage and continued seamlessly after it.")

    if env_subject_n and setting_pics:
        stext = _strip_article(b["setting"] or "environment shown")
        guard = ("" if any(r["role"] == "face" for r in setting_pics[0]["roles"])
                 else f"; no people from {ptag(setting_pics[0])} appear in the output")
        ra_lines.append(f"{_stag(env_subject_n)} (the setting, appears "
                        f"throughout): fully_preserved - the {stext} from "
                        f"{ptag(setting_pics[0])} is retained as the target "
                        f"video's setting{guard}.")

    for ref in b["pictures"]:
        labels, descs = [], []
        marker = None
        roles = ref["roles"]
        rolenames = [role["role"] for role in roles]
        has_start = "start frame" in rolenames and not loop
        attr_set = set(rolenames) & {"face", "hair", "outfit", "body", "appearance"}
        # 'only X is applied; Y is not used' phrasing is correct for a
        # single-attribute picture but self-contradictory when the same
        # picture supplies several attributes — H3 then drops some of them.
        solo = len(attr_set) == 1
        for role in roles:
            rn, targets = role["role"], role["targets"]
            tgt = _join([_stag(n) for n in targets]) if targets else ""
            if rn == "face":
                is_primary = not (role["note"] and "reinforc" in role["note"].lower()) \
                    and (role is next(r for r in roles if r["role"] == "face"))
                # primary/reinforcement per subject is decided in declaration
                # order across pictures; here we phrase by this picture's note
                if role["note"] and ("angle" in role["note"].lower()
                                     or "reinforc" in role["note"].lower()):
                    labels.append(f"face reinforcement for {tgt}")
                    descs.append("same face from another angle, used only to "
                                 "strengthen facial likeness")
                else:
                    labels.append(f"face source for {tgt}")
                    d = "the facial identity and features are retained exactly"
                    if ref.get("sheet"):
                        d = "every panel shows the same face; " + d
                    if (not has_start and "hair" not in attr_set
                            and any(_pic_roles_for(b, n, "hair") for n in targets)):
                        d += "; the hair in this picture is ignored and replaced"
                    descs.append(d)
                marker = marker or "partially_preserved"
            elif rn == "hair":
                labels.append(f"hair source for {tgt}")
                if solo:
                    descs.append(f"only the hairstyle and color are applied to {tgt}; "
                                 "the face in this picture is not used")
                else:
                    descs.append(f"the hairstyle and color are applied to {tgt}")
                marker = marker or "attribute_transfer"
            elif rn == "outfit":
                labels.append(f"outfit source for {tgt}")
                if solo:
                    descs.append(f"only the clothing is applied to {tgt}; the face "
                                 "and hair in this picture are not used")
                else:
                    descs.append(f"the clothing is applied to {tgt}")
                marker = marker or "attribute_transfer"
            elif rn == "body":
                labels.append(f"body source for {tgt}")
                if solo:
                    descs.append(f"only the body type, build, and proportions are "
                                 f"applied to {tgt}; the face and hair in this "
                                 "picture are not used")
                else:
                    descs.append(f"the body type, build, and proportions are "
                                 f"applied to {tgt}")
                marker = marker or "attribute_transfer"
            elif rn == "appearance":
                labels.append(f"appearance source for {tgt}")
                descs.append(f"the overall appearance is applied to {tgt}")
                marker = marker or "partially_preserved"
            elif rn == "setting":
                if env_subject_n:
                    continue  # subject mode: the <Subject K> entry covers it
                labels.append("setting")
                stext = _strip_article(b["setting"] or "environment")
                if any(r["role"] == "face" for r in roles):
                    descs.append(f"the {stext} is used as the setting")
                else:
                    descs.append(f"only the {stext} is used; no people from "
                                 "this picture appear in the output")
                marker = marker or "partially_preserved"
            elif rn == "object":
                note = role["note"] or "object"
                labels.append(f"object: {note}")
                descs.append(f"the {note} appears in the output as shown")
                marker = marker or "partially_preserved"
            elif rn == "start frame":
                pass  # handled below
        if ref.get("sheet"):
            labels.insert(0, "character sheet")
        # A picture supplying the overall appearance plus hair/outfit is
        # essentially the whole person minus (at most) the face. 'body' is
        # an attribute (build only), so body + hair stays a partial transfer.
        if "appearance" in attr_set and attr_set & {"hair", "outfit"}:
            marker = "fully_preserved"
        if has_start:
            labels.append("[Shot 1] first frame")
            descs.insert(0, "this image is the exact first frame of the video, "
                            "preserved entirely")
            marker = "fully_preserved"
        if not labels and has_start:
            labels = ["[Shot 1] first frame"]
        if labels:
            ra_lines.append(f"{ptag(ref)} ({', '.join(labels)}): {marker} - "
                            + "; ".join(descs) + ".")

    # Likeness videos are appearance sources, so they read like the picture
    # lines: the label names the bound subject, the exclusions fence out
    # motion/camera/setting so the clip is never treated as footage to keep.
    for ref in likeness_vids:
        targets = sorted({t for role in ref["roles"] if role["role"] == "likeness"
                          for t in role["targets"]})
        tgt = _join([_stag(t) for t in targets])
        note = _role_note(ref, "likeness")
        ra_lines.append(
            f"{vtag(ref)} (appearance source for {tgt}): fully_preserved - the "
            f"identity, face, hair, and overall appearance of the person in this "
            f"video are retained exactly for {tgt}; the video's actions, camera, "
            "framing, and setting are not used"
            + (f"; {note}" if note else "") + ".")

    def _ra_video_group(role_name, label, desc_fn):
        groups = {}
        for ref in b["videos"]:
            for role in ref["roles"]:
                if role["role"] == role_name:
                    groups.setdefault(tuple(role["targets"]), []).append(ref)
        for targets, refs in groups.items():
            tags = _join([vtag(r) for r in refs])
            tgt = _join([_stag(n) for n in targets])
            plural = "these videos" if len(refs) > 1 else "this video"
            ra_lines.append(f"{tags} ({label}): attribute_transfer - "
                            + desc_fn(tgt, plural) + ".")

    for ref in edit_vids:
        note = _role_note(ref, "edit source")
        desc = ("the target video is an edited version of this video; its "
                "scene, framing, camera movement, timing, and lighting are "
                "preserved except where the described edit changes them")
        if note:
            desc += f"; {note}"
        ra_lines.append(f"{vtag(ref)} (edit source): partially_preserved - {desc}.")
    for ref in scene_vids:
        snote = _role_note(ref, "setting")
        ra_lines.append(f"{vtag(ref)} (setting): fully_preserved - the "
                        "environment, background, and lighting of this video "
                        "are retained as the target video's setting; no person "
                        "from this video is an appearance source"
                        + (f"; {snote}." if snote else "."))

    _ra_video_group("body motion", "body motion", lambda tgt, pl:
                    f"the exact motions, timing, and pacing are applied to {tgt} "
                    f"from start to end; nothing of the appearance of the people "
                    f"in {pl} is used")
    # First declared audio that mouths actually sync to (bed/music-only refs
    # carry no voice, so mouth articulation must not claim sync to them)
    sync_auds = [ref for ref in b["audios"]
                 if any(r["role"] in ("soundtrack", "lipsync") for r in ref["roles"])]
    aud_tag = f"<Audio {aud_num[sync_auds[0]['id']]}>" if sync_auds else ""
    _ra_video_group("mouth", "mouth articulation", lambda tgt, pl:
                    f"all lip sync, mouth, and tongue movements are applied to {tgt}"
                    + (f", synchronized with {aud_tag}" if aud_tag else "")
                    + f"; the face in {pl} is never used for appearance")
    _ra_video_group("pose", "pose control", lambda tgt, pl:
                    f"the body poses are applied to {tgt}; nothing of the "
                    f"appearance of the people in {pl} is used")
    _ra_video_group("depth", "depth control", lambda tgt, pl:
                    f"the spatial arrangement guides {tgt}; nothing of the "
                    f"appearance in {pl} is used")

    for ref in b["audios"]:
        roles = {role["role"] for role in ref["roles"]}
        lp = next((role for role in ref["roles"] if role["role"] == "lipsync"), None)
        has_music = "music" in roles
        if "bed" in roles and not lp:
            if "offscreen voice" in roles:
                ra_lines.append(f"{atag(ref)}: partially_copy - the ambience, "
                                "music, and the off-screen speaker's voice are "
                                "used as-is; that voice belongs to no visible "
                                "subject; the visible subjects' spoken voices "
                                "are newly generated and are not part of this "
                                "audio.")
            else:
                ra_lines.append(f"{atag(ref)}: partially_copy - the ambience and "
                                "music are used as the background of the target "
                                "video; all spoken voices are newly generated and "
                                "are not part of this audio.")
        elif "soundtrack" in roles or (has_music and not lp):
            line = f"{atag(ref)}: fully_copy - used as the complete soundtrack " \
                "of the target video"
            if lp:
                joined = _join([_stag(n) for n in lp["targets"]])
                line += f"; when {joined} speaks with a visible mouth, " \
                    "synchronize that mouth to its attributed voice; " \
                    "off-screen speech remains off-screen"
            if has_music:
                line += ("; the background music is non-diegetic — no one "
                         "performs it on screen")
            ra_lines.append(line + ".")
        elif lp:
            ra_lines.append(f"{atag(ref)}: reference - "
                            f"{_join([_stag(n) for n in lp['targets']])} "
                            f"{_vocal_verb(lp)} with this voice; synchronize the mouth "
                            "when visible, preserving off-screen speech.")

    retention_analysis = "\n".join(ra_lines)

    # ---- detailed_description scaffolding ----
    # CONTROL videos only: a likeness clip is an appearance SOURCE and must
    # not sit in the 'never from' fence.
    all_vid_tags = ["<Video 1>"] if tail_ref else []
    all_vid_tags += [vtag(r) for r in b["videos"] if r not in likeness_vids]
    face_lock = None

    def _face_srcs(n):
        return ([ptag(r) for r, _ in _pic_roles_for(b, n, "face")]
                + [vtag(r) for r, _ in _vid_roles_for(b, n, "likeness")])

    face_subj = [n for n in subjects if _face_srcs(n)]
    if face_subj:
        never = f" — never from {_or_join(all_vid_tags)}" if all_vid_tags else ""
        if len(face_subj) == 1:
            n = face_subj[0]
            has_pic = bool(_pic_roles_for(b, n, "face"))
            has_vid = bool(_vid_roles_for(b, n, "likeness"))
            what = ("reference pictures" if not has_vid else
                    "reference pictures and video" if has_pic else "reference video")
            pron = _pron(b["subjects"][n]["desc"])
            face_lock = (f"{pron} face always matches the {what} "
                         f"exactly; facial appearance comes only from "
                         f"{_join(_face_srcs(n))}{never}.")
        else:
            clauses = _join([
                f"{_stag(n)}'s appearance comes only from " + _join(_face_srcs(n))
                for n in face_subj])
            refs_word = ("reference pictures" if not likeness_vids
                         else "reference pictures and videos")
            face_lock = (f"Each face always matches its {refs_word} "
                         f"exactly: {clauses}{never}.")

    # LoRA identity locks: one sentence per LoRA-defined subject, keeping the
    # trigger token present in detailed_description and fencing the control
    # videos out of that subject's appearance (mirrors face_lock).
    lora_locks = []
    for n in subjects:
        token = b["subjects"][n].get("lora")
        if not token:
            continue
        poss = _pron(b["subjects"][n]["desc"]).lower()
        if all_vid_tags:
            never = f"{_or_join(all_vid_tags)}"
        elif likeness_vids:
            never = "any control video"
        else:
            never = "any reference video"
        lora_locks.append(f"{_stag(n)} is {token} throughout; {poss} "
                          f"appearance never comes from {never}.")

    # Voice bindings permit lip sync only for the attributed, visible speaker.
    speech_lock = []
    lipsynced = set()
    # Subject number -> reference audio tag; independent of the voice ID.
    lipsync_audio = {}
    for ref in b["audios"]:
        lp = next((r for r in ref["roles"] if r["role"] == "lipsync"), None)
        if not lp:
            continue
        for n in lp["targets"]:
            lipsync_audio.setdefault(n, atag(ref))
        tgt = _join([_stag(n) for n in lp["targets"]])
        speech_lock.append(f"For the voices in {atag(ref)} attributed to {tgt}, "
                           "animate only the identified speaker's visible mouth in sync; "
                           "off-screen or unidentified speech does not make a listener speak.")
        lipsynced |= set(lp["targets"])
    # Bed audio (generated voices): every subject defaults to silent; the
    # per-chunk dialogue merge suppresses the lock for whoever speaks, so
    # speech happens exactly where dialogue lines exist.
    has_bed = any(any(r["role"] == "bed" for r in ref["roles"])
                  for ref in b["audios"])
    for ref in b["audios"]:
        ov = next((r for r in ref["roles"] if r["role"] == "offscreen voice"), None)
        if ov is not None:
            if ov["targets"]:
                # POV case: the voice's owner IS a subject whose body may be
                # in frame — only the face/mouth is never visible.
                tgt = _join([_stag(n) for n in ov["targets"]])
                poss = _pron(b["subjects"][ov["targets"][0]]["desc"]).lower()
                speech_lock.append(f"The off-screen voice in "
                                   f"<Audio {aud_num[ref['id']]}> is {tgt}'s: "
                                   f"{poss} face and mouth are never in frame, "
                                   "so the voice is heard without any visible "
                                   "mouth articulating it — never show a face "
                                   "or moving lips for it.")
            else:
                speech_lock.append(f"The off-screen voice in "
                                   f"<Audio {aud_num[ref['id']]}> belongs to no "
                                   "one on screen; no visible subject speaks, "
                                   "mouths, or lip-syncs it.")
    if lipsynced or has_bed:
        mouth_driven = {t for ref in b["videos"] for role in ref["roles"]
                        if role["role"] == "mouth" for t in role["targets"]}
        for n in subjects:
            if n in lipsynced:
                continue
            if n in mouth_driven:  # mouth guide may still move the lips
                speech_lock.append(f"{_stag(n)} does not speak; no voice in "
                                   f"the soundtrack is {_stag(n)}'s.")
            else:
                pron = _pron(b["subjects"][n]["desc"]).lower()
                speech_lock.append(f"{_stag(n)} does not speak and keeps "
                                   f"{pron} mouth closed.")

    if loop and tail_ref:
        opener = ("One continuous shot already in progress: the opening moments "
                  "are the existing footage of <Video 1>, and everything after "
                  "continues it seamlessly with no cut, jump, or reset.")
    elif loop:
        opener = ("One continuous shot already in progress: the opening moments "
                  "are existing footage, and everything after continues it "
                  "seamlessly with no cut, jump, or reset.")
    elif start_pics:
        opener = f"The video begins exactly at the frame of {ptag(start_pics[0])}."
    else:
        opener = None

    appends = list(b["appends"]["all"]) + list(b["appends"]["loop" if loop else "init"])

    # ---- soundscape + non-diegetic music ----
    sc_clauses, ndm_parts = [], []
    for ref in b["audios"]:
        roles = {r["role"] for r in ref["roles"]}
        lp = next((r for r in ref["roles"] if r["role"] == "lipsync"), None)
        has_music = "music" in roles
        tgt = _join([_stag(n) for n in lp["targets"]]) if lp else ""
        vw = "voices" if lp and len(lp["targets"]) > 1 else "voice"
        if "bed" in roles and not lp:
            if "offscreen voice" in roles:
                sc_clauses.append(f"{atag(ref)} provides the background "
                                  "ambience, music, and an off-screen voice "
                                  "(no visible speaker); the visible "
                                  "subjects' voices are newly generated over it")
            else:
                sc_clauses.append(f"{atag(ref)} provides the background ambience "
                                  "and music; the subjects' voices are newly "
                                  "generated over it")
        elif "soundtrack" in roles and lp:
            c = f"{atag(ref)} is the entire soundtrack, preserving its voices and their timing"
            sc_clauses.append(c + (" over background music" if has_music else ""))
        elif lp:
            sc_clauses.append(f"{atag(ref)} supplies {tgt}'s {vw}, with visibility specified per utterance")
        elif "soundtrack" in roles or has_music:
            sc_clauses.append(f"{atag(ref)} is the entire soundtrack"
                              + (": background music" if has_music else ""))
        if has_music:
            ndm_parts.append(f"The music in {atag(ref)} is non-diegetic "
                             "background music; no one performs it on screen.")
    if b["soundscape"]:
        soundscape = b["soundscape"]
    elif sc_clauses:
        soundscape = "; ".join(sc_clauses) + "; no additional sound is generated."
    else:
        soundscape = "The natural sounds of the scene."
    non_diegetic_music = " ".join(ndm_parts) or None

    # ---- substitution map (positional phrase -> subject tag) ----
    subs = build_subs_map([(_stag(n), b["subjects"][n]["desc"],
                            b["subjects"][n]["position"]) for n in subjects])

    # ---- guidance text (for VLM description rewrites) ----
    g = ["Subject bindings (use these tags, nothing else):"]
    for n in subjects:
        s = b["subjects"][n]
        line = f"- {_stag(n)}: {s['desc']}"
        if s["position"]:
            line += f" — appears in the draft as '{s['position']}'"
        if s.get("lora"):
            line += (f" — LoRA character '{s['lora']}': keep this token "
                     "verbatim; never add appearance details for this subject")
        g.append(line)
    if env_subject_n:
        g.append(f"- {_stag(env_subject_n)}: the setting"
                 + (f" ({b['setting']})" if b["setting"] else "")
                 + " — use this tag when referencing the environment")
    if tail_ref:
        g.append("- <Video 1> is the carried tail of the previous chunk "
                 "(existing footage), never an appearance source.")
    whole_video_guidance = {
        "edit source": "the source video being edited — the target video is "
                       "an edited version of it",
        "setting": "supplies the setting; its environment is kept in the "
                   "target video",
    }

    def _vid_role_guidance(role):
        if role["role"] in whole_video_guidance:
            return whole_video_guidance[role["role"]]
        if role["role"] == "likeness":
            tgt = _join([_stag(t) for t in role["targets"]]) or "the subject"
            return (f"identity and appearance source for {tgt} (face, hair, "
                    "overall look — treat it like a reference picture); never "
                    "a motion, camera, or setting source")
        if not role["targets"]:
            return role["role"]
        return f"{role['role']} of {_join([_stag(t) for t in role['targets']])}"

    for ref in b["videos"]:
        g.append(f"- {vtag(ref)}: "
                 + "; ".join(_vid_role_guidance(role) for role in ref["roles"]))
    for ref in b["audios"]:
        lp = next((r for r in ref["roles"] if r["role"] == "lipsync"), None)
        if lp:
            g.append(f"- {atag(ref)}: dialogue for {_join([_stag(t) for t in lp['targets']])}; "
                     "preserve voice IDs and each utterance's on-screen/off-screen visibility")
    guidance = "\n".join(g)

    return {
        "subject_definitions": subject_definitions,
        "summary": summary,
        "retention_analysis": retention_analysis,
        "face_lock": face_lock,
        "lora_locks": lora_locks,
        "speech_lock": speech_lock,
        "lipsync_audio": lipsync_audio,
        "soundtrack_audio": next((atag(ref) for ref in b["audios"]
                                  if any(r["role"] == "soundtrack" for r in ref["roles"])), None)
                            if sum(any(r["role"] == "soundtrack" for r in ref["roles"])
                                   for ref in b["audios"]) == 1 else None,
        "non_diegetic_music": non_diegetic_music,
        "opener": opener,
        "appends": appends,
        "soundscape": soundscape,
        "subs_map": subs,
        "appositions": {_stag(n): apposition_phrase(b["subjects"][n]["desc"],
                                                    b["subjects"][n]["position"],
                                                    b["subjects"][n].get("lora"))
                        for n in subjects},
        "guidance": guidance,
        "video_numbers": {k: v for k, v in vid_num.items()},
        "audio_numbers": {k: v for k, v in aud_num.items()},
    }

def _mmss(sec):
    sec = max(float(sec), 0.0)
    m, s = divmod(sec, 60.0)
    return f"{int(m):02d}:{s:06.3f}"

_SILENCE_LOCK = re.compile(r"^<Subject (\d+)> does not speak")

def filter_speech_lock(speech_lock, speaking):
    """Drop per-subject 'does not speak' locks for subjects that actually
    speak this chunk (dialogue wins over the phase-wide silence default);
    positive 'The voice in <Audio k> belongs to ...' locks always pass."""
    if not speaking:
        return list(speech_lock)
    out = []
    for s in speech_lock:
        m = _SILENCE_LOCK.match(s)
        if m and int(m.group(1)) in speaking:
            continue
        out.append(s)
    return out

_SHOT_NOTE = re.compile(r"\[shot boundary note:(?:[^\[\]]|\[[^\[\]]*\])*\]",
                        re.IGNORECASE)

_CUT_TIMES = re.compile(r"\bcut at\s*(\d+:\d+(?:\.\d+)?(?:\s*,\s*\d+:\d+(?:\.\d+)?)*)",
                        re.IGNORECASE)

_SHOT_HEADER = re.compile(
    r"\[Shot \d+\]\s*(?:(?:At\s+|starts at\s+)?(\d+:\d+(?:\.\d+)?)[,.]?\s*)?",
    re.IGNORECASE)

_CUT_CUE = re.compile(
    r"\b(?:after (?:the |a )?(?:hard |black |scene )?cut\b|"
    r"(?:the )?(?:shot|scene|view|framing|camera) (?:hard[- ]cuts|cuts)\b)",
    re.IGNORECASE)

def format_shots(body, cut_notes=""):
    """Consume draft metadata and put guide headings on the actual shot prose."""
    times = []
    for note in _SHOT_NOTE.finditer(cut_notes or body):
        match = _CUT_TIMES.search(note.group())
        if match:
            for stamp in match[1].split(","):
                minutes, seconds = stamp.strip().split(":")
                stamp = _mmss(int(minutes) * 60 + float(seconds))
                if stamp not in times:
                    times.append(stamp)

    def remove_note(match):
        # Short inline notes already identify the prose's exact split point.
        if re.match(r"\[shot boundary note:\s*cut at", match.group(), re.IGNORECASE):
            stamp = _CUT_TIMES.search(match.group())
            if stamp and "," not in stamp[1]:
                return "\n[Shot 2] At " + stamp[1] + ", "
        return ""

    text = _SHOT_NOTE.sub(remove_note, body).strip()
    first = _SHOT_HEADER.search(text)
    if not first or (first.start() > 0 and not first.group().lower().startswith("[shot 1]")):
        text = "[Shot 1] " + text
    missing = len(times) + 1 - len(list(_SHOT_HEADER.finditer(text)))
    if missing > 0:
        # Older drafts are one paragraph. Split only at explicit cut language,
        # never at a pan, zoom, action change, or guessed word-count position.
        dialogue = [m.span() for m in re.finditer(r"<d>.*?</d>", text, re.DOTALL)]
        cues = [m for m in _CUT_CUE.finditer(text)
                if not any(a <= m.start() < b for a, b in dialogue)]
        if len(cues) == missing:
            for cue in reversed(cues):
                before = text[:cue.start()].rstrip(" ,;")
                stop = "" if before.endswith((".", "!", "?")) else "."
                text = before + stop + "\n[Shot 2] " + text[cue.start():]
        else:
            # A cached caption may omit the new view entirely. Keep the known
            # cut without inventing its composition; a redo supplies that detail.
            print("[H3Compose] Draft lacks separate prose for a detected shot; "
                  "redo this description for shot-specific detail.")
            text += "\n[Shot 2] The shot cuts to the next view." * missing

    headers = list(_SHOT_HEADER.finditer(text))
    blocks = [text[:headers[0].start()].strip()]
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        prose = text[header.end():end].strip()
        if i == 0:
            blocks.append("[Shot 1] " + prose)
            continue
        stamp = times[i - 1] if i <= len(times) else header[1]
        if stamp:
            minutes, seconds = stamp.split(":")
            stamp = _mmss(int(minutes) * 60 + float(seconds))
            transition = "" if _CUT_CUE.match(prose) else "the shot cuts. "
            blocks.append(f"[Shot {i + 1}] At {stamp}, {transition}{prose}")
        else:
            blocks.append(f"[Shot {i + 1}] {prose}")
    return "\n".join(block for block in blocks if block)

_POSITION_SYN_GROUPS = (
    ("on top", "on the top", "above", "up top"),
    ("on the bottom", "at the bottom", "beneath", "underneath", "below"),
    ("in front", "at the front", "in the front", "in the foreground",
     "closest to the camera", "nearest the camera"),
    ("behind", "at the back", "in the back", "in the background",
     "farthest from the camera", "furthest from the camera"),
)

_ADJ_FORMS = (
    ("on top", "upper"), ("on the top", "upper"), ("above", "upper"),
    ("on the bottom", "lower"), ("at the bottom", "lower"),
    ("beneath", "lower"), ("underneath", "lower"), ("below", "lower"),
    ("on the left", "left"), ("on the right", "right"),
)

_PERSON_NOUN = r"(?:woman|man|person|girl|lady|guy|boy)"

def expand_position_phrase(pos):
    """One declared position phrase -> tolerant variant set: person-noun
    swaps (woman/person/girl/lady, man/person/guy), spatial-synonym families
    (top/above, bottom/beneath, front/foreground, behind/background), and
    adjective forms ('the upper woman'). Variants are match KEYS — a
    nonsensical generated phrase simply never matches."""
    variants = {pos}
    for a, bb in (("woman", "person"), ("man", "person"), ("woman", "girl"),
                  ("woman", "lady"), ("man", "guy")):
        variants |= {re.sub(rf"\b{a}\b", bb, v, flags=re.IGNORECASE)
                     for v in list(variants)}
    for group in _POSITION_SYN_GROUPS:
        for v in list(variants):
            for member in group:
                pat = re.compile(rf"\b{re.escape(member)}\b", re.IGNORECASE)
                if pat.search(v):
                    variants |= {pat.sub(repl, v) for repl in group
                                 if repl != member}
                    break
    adj = set()
    for v in variants:
        for phrase, a in _ADJ_FORMS:
            pat = re.compile(rf"\b({_PERSON_NOUN})\s+{re.escape(phrase)}\b",
                             re.IGNORECASE)
            if pat.search(v):
                adj.add(pat.sub(rf"{a} \1", v))
    return variants | adj

def build_subs_map(entries):
    """(tag, desc, position) triples -> {phrase: tag} for apply_substitutions.

    Positional phrases are expanded via expand_position_phrase (noun swaps,
    spatial synonyms, adjective forms). With exactly ONE subject there is no
    ambiguity, so bare generic names ('the woman', 'the person') map to that
    subject too — gendered nouns only when they match the subject's own
    description, so a stray 'the man' in a single-woman scene is never
    mis-tagged."""
    subs = {}
    tags = set()
    for tag, desc, pos in entries:
        tags.add(tag)
        if not pos:
            continue
        for v in expand_position_phrase(pos):
            subs[v.lower()] = tag
    if len(tags) == 1 and entries:
        tag = next(iter(tags))
        pron = _pron(" ".join(f"{d or ''} {p or ''}" for _, d, p in entries))
        nouns = {"person"}
        if pron == "Her":
            nouns |= {"woman", "girl", "lady"}
        elif pron == "His":
            nouns |= {"man", "guy", "boy"}
        for noun in nouns:
            subs.setdefault(f"the {noun}", tag)
    return subs

def _flex_pattern(phrase):
    """Compile a positional phrase into a tolerant regex: interchangeable
    leading article (the/a/an) and preposition (on/at/to), and optional
    '-hand'/'side (of the frame/screen)' after left/right — so 'a woman at
    the left-hand side of the frame' still hits 'the woman on the left'."""
    parts = []
    for i, tok in enumerate(phrase.split()):
        low = tok.lower()
        if i == 0 and low in ("the", "a", "an"):
            parts.append(r"(?:the|a|an)")
        elif low in ("on", "at", "to"):
            parts.append(r"(?:on|at|to)")
        elif low in ("left", "right"):
            parts.append(re.escape(low)
                         + r"(?:\s*-?\s*hand)?(?:\s+side)?"
                         + r"(?:\s+of\s+the\s+(?:frame|screen|shot|image))?")
        else:
            parts.append(re.escape(tok))
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)

def apply_substitutions(text, subs_map):
    """Replace positional person phrases with <Subject N> tags (tolerant
    matching via _flex_pattern; longest phrases first so 'the woman on the
    left' wins over a bare 'the woman' entry)."""
    for phrase in sorted(subs_map, key=len, reverse=True):
        text = _flex_pattern(phrase).sub(subs_map[phrase], text)
    # "the <Subject 1>" -> "<Subject 1>"
    text = re.sub(r"\b[Tt]he\s+(<Subject \d+>)", r"\1", text)
    return text

_APPO_TAIL_PREPS = ("on", "at", "in", "to", "by", "near", "behind", "beneath",
                    "underneath", "above", "below", "closest", "nearest",
                    "farthest", "furthest")

_APPO_RE = re.compile(
    rf"(?P<tag><Subject \d+>(?:\s*\(S\d+\))?),\s+(?:the|a|an)\s+"
    rf"[^,<>]{{0,90}}?\b{_PERSON_NOUN}\b[^,<>]{{0,60}}?,")

def strip_appositions(text):
    """Remove composer-generated first-mention appositions from prose."""
    return _APPO_RE.sub(lambda m: m.group("tag"), text)

def _position_tail(pos):
    """'the woman on the left' -> 'on the left'; 'the person kneeling' ->
    'kneeling'; unparseable/empty -> None."""
    m = re.match(rf"^(?:the|a|an|one)?\s*(?:[a-z-]+\s+){{0,2}}?{_PERSON_NOUN}\s+(.+)$",
                 (pos or "").strip(), re.IGNORECASE)
    return m.group(1).strip() if m else None

def apposition_phrase(desc, position, lora=None):
    """Binding desc/position -> the first-mention apposition text, or None.

    Non-LoRA subjects: first sentence of the binding desc ('naked woman with
    brown curly hair' -> 'the naked woman with brown curly hair') + the
    positional tail ('on the left'). LoRA subjects: position phrase only —
    their appearance comes from the LoRA token, never from prose."""
    if lora:
        return (position or "").strip() or None
    first = re.split(r"(?<=[.!?])\s", (desc or "").strip())[0].strip().rstrip(".!?")
    first = re.sub(r"\s+", " ", first)
    if not first:
        return (position or "").strip() or None
    # Contrast-desc bindings are ONE long comma-joined sentence (60-80 words);
    # a first-mention apposition must stay a short re-anchor (guide §5.3), so
    # cap long descs at the leading comma segments within ~12 words (the head
    # clause always survives). Short classic descs pass through unchanged.
    if len(first.split()) > 14:
        segs = first.split(", ")
        kept = segs[0]
        for seg in segs[1:]:
            if len(kept.split()) + len(seg.split()) > 12:
                break
            kept += ", " + seg
        first = kept
    if len(first) > 1 and first[1:2].islower():
        first = first[0].lower() + first[1:]
    m = re.match(r"^(?:a|an)\s+(.*)$", first, re.IGNORECASE)
    if m:
        first = "the " + m.group(1)
    elif not re.match(r"^the\b", first, re.IGNORECASE):
        first = "the " + first
    tail = _position_tail(position)
    if tail:
        joiner = " " if tail.split()[0].lower() in _APPO_TAIL_PREPS else ", "
        first += joiner + tail
    return first

def insert_appositions(text, appositions):
    """Insert each subject's apposition at its first suitable tag mention:
    skips possessives (<Subject 1>'s) and sentence-final mentions (a
    comma-terminated clause must fit — see _APPO_RE), lands after a speaker
    id ((Sx)), and backs off if the mention already carries an appositive."""
    for tag in sorted(appositions):
        appo = appositions[tag]
        if not appo:
            continue
        for m in re.finditer(re.escape(tag) + r"(?:\s*\(S\d+\))?", text):
            end = m.end()
            rest = text[end:]
            if re.match(r",\s*(?:the|a|an)\b", rest):
                break  # already appositioned
            if rest.startswith("'") or re.match(r"\s*[.;:!?,]", rest):
                # possessive / punctuation-followed — a clean comma-terminated
                # clause can't be inserted here; try the next mention
                continue
            text = text[:end] + f", {appo}," + rest
            break
    return text

def _interleave_dialogue(text, sentences):
    """Place an utterance in the shot containing its onset, keeping its full span."""
    shots = list(re.finditer(r"\[Shot \d+\]\s*(?:(?:At )?(\d+):(\d+(?:\.\d+)?))?", text))
    if len(shots) < 2:
        return " ".join([text.strip(), *sentences]).strip()
    starts = [int(m[1]) * 60 + float(m[2]) if m[1] else 0 for m in shots]
    blocks = [text[m.start():shots[i + 1].start() if i + 1 < len(shots) else len(text)].strip()
              for i, m in enumerate(shots)]
    index = 0
    for sentence in sentences:
        m = re.match(r"(?:From|At) (\d+):(\d+(?:\.\d+)?)", sentence)
        if m:
            t = int(m[1]) * 60 + float(m[2])
            index = max((i for i, start in enumerate(starts) if start <= t), default=0)
        blocks[index] += " " + sentence
    prefix = text[:shots[0].start()].strip()
    return "\n".join(([prefix] if prefix else []) + blocks)

def format_description(body, compiled, substitute=True, extra_sentences=(),
                       dialogue_sentences=(), speaking_subjects=(),
                       apposition=False, has_cuts=False, cut_notes=""):
    """Draft/pre-existing prose -> final detailed_description text.

    dialogue_sentences: pre-formatted 'At MM:SS.mmm <Subject N> (SN) says
    <d>...</d>.' sentences inserted into the matching shot (never touched
    by substitutions or scrubbing). speaking_subjects: subject numbers that
    speak this chunk — their 'does not speak' silence locks are suppressed.
    apposition: insert each subject's guide-style first-mention re-anchor
    ('<Subject 1>, the naked woman with brown curly hair on the left, ...')
    built from the bindings; stale appositions are stripped either way."""
    has_cuts = (has_cuts or bool(cut_notes) or "[shot boundary note:" in body.lower()
                or bool(re.search(r"\[Shot (?:[2-9]|\d{2,})\]", body, re.IGNORECASE)))
    text = strip_appositions(body.strip())
    if substitute:
        text = apply_substitutions(text, compiled["subs_map"])
    if apposition:
        text = insert_appositions(text, compiled.get("appositions", {}))
    text = format_shots(text, cut_notes)
    pieces = []
    opener = compiled["opener"]
    if has_cuts and opener and opener.startswith("One continuous shot"):
        footage = ("the existing footage of <Video 1>"
                   if "footage of <Video 1>" in opener else "existing footage")
        opener = (f"The footage is already in progress: the opening moments are {footage}; "
                  "preserve the documented scene cuts at the stated times, "
                  "and continue each shot without additional cuts, jumps, or resets.")
    if opener:
        text = text.replace("[Shot 1] ", "[Shot 1] " + opener + " ", 1)
    pieces.append(_interleave_dialogue(text, dialogue_sentences))
    pieces += list(extra_sentences)
    if compiled["face_lock"]:
        pieces.append(compiled["face_lock"])
    pieces += compiled.get("lora_locks", ())
    pieces += filter_speech_lock(compiled.get("speech_lock", ()),
                                 set(speaking_subjects))
    pieces += compiled["appends"]
    return re.sub(r"[ \t]{2,}", " ", " ".join(pieces))

def compose_chunk(compiled, description):
    text = ("subject_definitions:\n" + compiled["subject_definitions"] + "\n\n"
            "summary:\n" + compiled["summary"] + "\n\n"
            "retention_analysis:\n" + compiled["retention_analysis"] + "\n\n"
            "detailed_description: " + description + "\n\n"
            "overall_soundscape: " + compiled["soundscape"])
    if compiled.get("non_diegetic_music"):
        text += "\n\nnon_diegetic_music: " + compiled["non_diegetic_music"]
    return text
