"""Deterministic H3 character-sheet prompt builders, extracted from vlm_video_prompt."""
import re
from .h3_format import DSLError, LOOP_TAIL_DEFAULT, parse_bindings, compile_phase, format_description, compose_chunk

def _clean_frag(text):
    """Widget text -> safe single DSL line fragment."""
    return re.sub(r"\s+", " ", (text or "").replace("#", "")).strip().rstrip(".")


_PIC_ROLE_CHOICES = ["unused", "face", "face (primary)", "face + hair",
                     "face + body", "face sheet", "character sheet", "hair",
                     "hair + body", "body", "outfit", "appearance",
                     "setting", "start frame", "object"]
# 'X + Y' choices compile to one multi-role DSL line ('face -> 1; hair -> 1');
# the picture note rides the FIRST role only (a shared note would be echoed
# on every fragment). 'body' = build/proportions only; 'appearance' = the
# whole look minus the face.
_VID_ROLE_CHOICES = ["unused", "body motion", "pose", "depth", "mouth", "likeness",
                     "edit source", "setting"]
_AUD_ROLE_CHOICES = ["unused", "soundtrack + lipsync", "soundtrack only",
                     "lipsync only", "music only",
                     "background bed (voices generated)",
                     "bed + off-screen voice (kept)"]
_TARGET_CHOICES = ["subject 1", "subject 2", "subject 3", "all"]


class H3Subjects:
    @classmethod
    def INPUT_TYPES(cls):
        d = {}
        for i in (1, 2, 3):
            req = "" if i > 1 else "a woman"
            pos = "the woman on the left" if i == 1 else ""
            d[f"subject{i}_description"] = ("STRING", {"default": req, "multiline": True, "tooltip": f"Who <Subject {i}> is, in words. Leave EMPTY to disable subject {i}."})
            d[f"subject{i}_position"] = ("STRING", {"default": pos, "tooltip": "How the draft names them positionally ('the woman on the left') — substituted to the <Subject N> tag at compose time."})
            d[f"subject{i}_lora"] = ("STRING", {"default": "", "tooltip": "LoRA trigger token (e.g. 'emie') for a LoRA-defined subject. Leave empty for picture-defined subjects. Remember to enable the character LoRA in the sampler workflow."})
        d["setting"] = ("STRING", {"default": "an apartment interior", "tooltip": "The setting in words. Bind a picture to it with a 'setting' role in H3 Ref Slots."})
        d["loop_tail"] = (["latent_anchor", "video_ref"], {"default": "latent_anchor", "tooltip": "How extension chunks carry the previous chunk's tail. latent_anchor (default): tail rides the latent-anchor nodes; videos/audios number from 1. video_ref: legacy graphs feeding the tail as ref_video_0; <Video 1>/<Audio 1> are reserved for it."})
        d["extra_rules"] = ("STRING", {"default": "", "multiline": True, "tooltip": "Camera/visibility locks appended to EVERY chunk's detailed_description, one per line — e.g. a POV lock: 'The entire video is a first-person POV shot from <Subject 2>'s eyes; his face, head, and neck are never visible in any frame.' Survives rebinds; never scrubbed."})
        # Appended LAST (positional widget restore safety for saved graphs)
        d["setting_as_subject"] = ("BOOLEAN", {"default": False, "tooltip": "Official-guide §2.2 setting form: the environment becomes its own <Subject K> (next free number) citing the setting picture inline ('<Subject 3> is <setting text>, the environment shown in <Picture 9>.'), with a subject-tagged fully_preserved retention line and 'in <Subject 3>' in the summary — instead of the standalone '<Picture 9> defines the setting' line. Only takes effect when a picture has the 'setting' role."})
        return {"required": d}

    RETURN_TYPES = ("H3_SUBJECTS",)
    RETURN_NAMES = ("subjects",)
    FUNCTION = "build"
    CATEGORY = "prompt/vlm"
    DESCRIPTION = "Structured subject entry for H3 bindings (no DSL syntax): up to 3 subjects with position + optional LoRA trigger token, the setting text, and the loop-tail mode. Wire into H3 Ref Slots."

    def build(self, **kw):
        lines = []
        for i in (1, 2, 3):
            desc = _clean_frag(kw.get(f"subject{i}_description"))
            if not desc:
                continue
            line = f"subject {i}: {desc}"
            pos = _clean_frag(kw.get(f"subject{i}_position"))
            lora = _clean_frag(kw.get(f"subject{i}_lora"))
            if lora:
                line += f" ; lora: {lora}"
            if pos:
                line += f" ; position: {pos}"
            lines.append(line)
        if not lines:
            raise ValueError("H3Subjects: subject 1's description is empty — "
                             "at least one subject is required")
        setting = _clean_frag(kw.get("setting"))
        if setting:
            lines.append(f"setting: {setting}")
        if kw.get("setting_as_subject"):
            lines.append("setting mode: subject")
        lines.append(f"loop tail: {kw.get('loop_tail', 'latent_anchor')}")
        for raw in (kw.get("extra_rules") or "").splitlines():
            rule = re.sub(r"^append\s+(all|init|loop)\s*:\s*", "", raw.replace("#", "").strip(),
                          flags=re.IGNORECASE)
            scope = "all"
            m = re.match(r"^append\s+(all|init|loop)\s*:", raw.strip(), re.IGNORECASE)
            if m:
                scope = m.group(1).lower()
            if rule:
                lines.append(f"append {scope}: {rule}")
        return ("\n".join(lines),)


class H3RefSlots:
    """Combo-driven role assignment for the sampler's fixed ref slots."""

    @classmethod
    def INPUT_TYPES(cls):
        d = {"subjects": ("H3_SUBJECTS",)}
        for i in range(1, 10):
            role_def = "setting" if i == 9 else ("character sheet" if i == 1 else "unused")
            d[f"pic_{i}"] = (_PIC_ROLE_CHOICES, {"default": role_def, "tooltip": f"Role of the sampler's ref image slot {i} (<Picture {i}> in your prompts). 'body' = body type/build/proportions only (face + hair in the picture are not used); 'appearance' = the whole look minus the face. 'face + hair' / 'face + body' / 'hair + body' take both attributes from this one picture."})
            d[f"pic_{i}_for"] = (_TARGET_CHOICES, {"default": "subject 1", "tooltip": "Which subject(s) this picture binds to. Ignored for 'setting' / 'start frame'."})
        vid_defaults = {1: "body motion", 2: "pose", 3: "mouth"}
        for i in range(1, 4):
            d[f"video_{i}"] = (_VID_ROLE_CHOICES, {"default": vid_defaults[i], "tooltip": f"Role of video slot {i} (Ctrl {'ABC'[i - 1]}, <Video {i}>). 'likeness' = the target subject IS the person in this clip (identity/appearance source like a picture, never motion) — on the sampler side feed such a clip as a STATIC ref (MMH3 MultiPrompt static_ref_videos) so every chunk sees the whole clip."})
            d[f"video_{i}_for"] = (_TARGET_CHOICES, {"default": "all"})
        d["audio_1"] = (_AUD_ROLE_CHOICES, {"default": "soundtrack + lipsync", "tooltip": "Role of the reference audio (<Audio 1>)."})
        d["audio_1_lipsync_by"] = (_TARGET_CHOICES + ["none (not a subject)"], {"default": "subject 1", "tooltip": "Whose voice the audio's speech is. For 'bed + off-screen voice': the subject whose face is never in frame (POV camera-man) — or 'none' when the voice belongs to nobody visible at all."})
        # New widgets go in optional AND at the end: saved workflows restore
        # widget values positionally, so inserting above would shift old saves.
        opt = {}
        for i in range(1, 4):
            opt[f"video_{i}_note"] = ("STRING", {"default": "", "tooltip": f"Optional note for video slot {i}, embedded as '(note)' in its binding line. Used by 'edit source' — the scope of the edit, what is replaced vs kept (e.g. 'only the woman on the left is replaced') — by 'setting' (extra environment detail) and by 'likeness' (a qualifier, e.g. 'front-facing interview'). Ignored for motion/pose/depth/mouth roles."})
        # pic notes appended AFTER the video notes (positional-restore safety)
        for i in range(1, 10):
            opt[f"pic_{i}_note"] = ("STRING", {"default": "", "tooltip": f"Optional note for picture slot {i}, embedded as '(note)'. For 'object': what the object IS — e.g. 'red ceramic vase', no leading article (renders as 'the <note> appears in the output as shown'). For hair/outfit/face/body: a qualifier like 'side profile' or 'another angle'. On a 'face + …' / 'hair + body' choice the note rides the first role only ('primary' here marks the face as the primary face source)."})
        return {"required": d, "optional": opt}

    RETURN_TYPES = ("H3_BINDINGS", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("bindings", "dsl_text", "preview_init", "preview_loop", "guidance")
    FUNCTION = "build"
    CATEGORY = "prompt/vlm"
    DESCRIPTION = "Assign roles to the sampler's 9 picture / 3 video / 1 audio slots with dropdowns and compile the H3 bindings — the structured replacement for hand-written DSL. dsl_text shows the equivalent DSL (copy it into H3 Ref Bindings for exotic cases)."

    @staticmethod
    def _target(sel):
        return "all" if sel == "all" else sel.split()[-1]

    @staticmethod
    def _clean_note(note):
        """Free-text note -> safe DSL '(note)' payload: strip chars the line
        grammar reserves (comment '#', role separators ';'/',' and parens)."""
        note = re.sub(r"[\n\r#()]", " ", note or "")
        note = re.sub(r"\s*[;,]\s*", " — ", note)
        return re.sub(r"\s+", " ", note).strip()

    def build(self, subjects, **kw):
        lines = [subjects.strip()] if (subjects or "").strip() else []
        for i in range(1, 10):
            role = kw.get(f"pic_{i}", "unused")
            if role == "unused":
                continue
            tgt = self._target(kw.get(f"pic_{i}_for", "subject 1"))
            note = self._clean_note(kw.get(f"pic_{i}_note"))
            suffix = f" ({note})" if note else ""
            if role in ("setting", "start frame", "object"):
                lines.append(f"picture {i}: {role}{suffix}")
            elif role == "face (primary)":
                # keep the 'primary' marker — the compiler detects it in the note
                marker = f"primary — {note}" if note else "primary"
                lines.append(f"picture {i}: face -> {tgt} ({marker})")
            elif " + " in role:
                # composite choice -> one line, one segment per role; the
                # note attaches to the first role only ('primary' in it
                # still marks a 'face + …' picture's face as primary)
                first, *rest = role.split(" + ")
                segs = [f"{first} -> {tgt}{suffix}"] + [f"{r} -> {tgt}" for r in rest]
                lines.append(f"picture {i}: " + "; ".join(segs))
            else:
                lines.append(f"picture {i}: {role} -> {tgt}{suffix}")
        for i in range(1, 4):
            role = kw.get(f"video_{i}", "unused")
            if role == "unused":
                continue
            note = self._clean_note(kw.get(f"video_{i}_note"))
            suffix = f" ({note})" if note else ""
            if role in ("edit source", "setting"):
                lines.append(f"video {i}: {role}{suffix}")
            else:
                tgt = self._target(kw.get(f"video_{i}_for", "all"))
                lines.append(f"video {i}: {role} -> {tgt}{suffix}")
        aud = kw.get("audio_1", "unused")
        if aud != "unused":
            by_sel = kw.get("audio_1_lipsync_by", "subject 1")
            no_subject = by_sel.startswith("none")
            by = "subject 1" if no_subject else self._target(by_sel)
            if no_subject and aud in ("soundtrack + lipsync", "lipsync only"):
                raise ValueError("H3RefSlots: a lipsync voice needs a subject "
                                 "owner — 'none' is only for the off-screen "
                                 "voice option")
            ov = "offscreen voice" if no_subject else f"offscreen voice -> {by}"
            aud_line = {"soundtrack + lipsync": f"audio 1: soundtrack; lipsync -> {by}",
                        "soundtrack only": "audio 1: soundtrack",
                        "lipsync only": f"audio 1: lipsync -> {by}",
                        "music only": "audio 1: music",
                        "background bed (voices generated)": "audio 1: bed",
                        "bed + off-screen voice (kept)": f"audio 1: bed; {ov}"}[aud]
            lines.append(aud_line)

        dsl_text = "\n".join(lines) + "\n"
        try:
            b = parse_bindings(dsl_text)
        except DSLError as e:
            raise ValueError(f"H3RefSlots: {e}\n--- generated DSL ---\n{dsl_text}") from e
        previews = {}
        for phase in ("init", "loop"):
            c = compile_phase(b, phase)
            previews[phase] = compose_chunk(
                c, format_description("(per-chunk motion description goes here)",
                                      c, substitute=False))
        guidance = compile_phase(b, "init")["guidance"]
        n_refs = len(b["pictures"]) + len(b["videos"]) + len(b["audios"])
        print(f"[H3RefSlots] {len(b['subjects'])} subject(s), {n_refs} reference(s), "
              f"loop_tail={b.get('loop_tail', LOOP_TAIL_DEFAULT)}")
        return (b, dsl_text, previews["init"], previews["loop"], guidance)


class H3ImagePromptCompose:
    """Single-image composer: bindings + ONE main description -> one
    six-section H3 guide prompt (subject_definitions / summary /
    retention_analysis / detailed_description / overall_soundscape).

    Built for the "H3 Single Image" flow: video/audio bindings are stripped
    (a still has no control videos and no reference soundtrack), the init
    phase is compiled, and the description becomes detailed_description.
    Picture numbers in the bindings must match the MMH3ImageList socket
    order (<Picture 1> = image_0, etc.).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bindings": ("H3_BINDINGS", {"tooltip": "From H3 Ref Slots (or H3 Ref Bindings). Video/audio bindings are ignored for a still."}),
                "description": ("STRING", {"default": "", "multiline": True, "tooltip": "The main prompt: what the image shows. Refer to people as <Subject N> (or their positional names from H3 Subjects) — the binding sentences tying subjects to <Picture i> refs are generated for you."}),
                "static_camera": ("BOOLEAN", {"default": True, "tooltip": "Append a locked-off-camera sentence so the 5-frame clip holds still and every latent slice decodes the same crisp frame."}),
            },
            "optional": {
                "soundscape_override": ("STRING", {"default": "", "tooltip": "Replace the compiled overall_soundscape line (the section is required by the guide format even for a still). Empty = keep the compiled default."}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "report")
    FUNCTION = "compose"
    CATEGORY = "prompt/vlm"
    DESCRIPTION = "Compose ONE H3-guide six-section prompt for single-image generation from subject/picture bindings + a main description. Wire prompt into MMH3ReferenceMultiPrompt (or the core r2v node)."

    def compose(self, bindings, description, static_camera, soundscape_override=""):
        import copy as _copy
        desc = re.sub(r"\s+", " ", (description or "")).strip()
        if not desc:
            raise ValueError("H3ImagePromptCompose: description is empty")
        b = _copy.deepcopy(bindings)
        dropped = len(b.get("videos", [])) + len(b.get("audios", []))
        b["videos"], b["audios"] = [], []
        if static_camera:
            if not desc.endswith((".", "!", "?")):
                desc += "."
            desc += (" The camera is locked off and static; the scene holds "
                     "still with no camera motion.")
        compiled = compile_phase(b, "init")
        if (soundscape_override or "").strip():
            compiled["soundscape"] = soundscape_override.strip()
        prompt = compose_chunk(compiled, desc)
        report = (f"{len(b['subjects'])} subject(s), {len(b['pictures'])} "
                  f"picture ref(s)"
                  + (f"; stripped {dropped} video/audio binding(s)" if dropped else "")
                  + ". Picture numbers must match MMH3ImageList socket order.")
        print(f"[H3ImagePromptCompose] {report}")
        return (prompt, report)

