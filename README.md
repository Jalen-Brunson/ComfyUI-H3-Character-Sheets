# H3 Character Sheets

A ComfyUI workflow for turning 1–9 references into one character sheet, with a standalone deterministic prompt-binding pack.

## Install

Clone this repository into `ComfyUI/custom_nodes/ComfyUI-H3-Character-Sheets`. It registers only `H3Subjects`, `H3RefSlots` and `H3ImagePromptCompose`; it has no extra Python dependencies and does not download or load a VLM. Install the other four packs linked below, restart ComfyUI, then open the JSON in `example_workflows`.

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Jalen-Brunson/ComfyUI-H3-Character-Sheets.git
git clone https://github.com/ckinpdx/ComfyUI-MMH3Tools.git
git clone https://github.com/scottmudge/ComfyUI_MinimaxH3HybridLoader.git
git clone https://github.com/shootthesound/ComfyUI-Fizgig-H3-Still.git
git clone https://github.com/yolain/ComfyUI-Easy-Use.git
```


## START HERE - H3 Character Sheets

### One character, one generated sheet
1. Install the packs listed in **Dependencies** and select your model files.
2. Upload **Picture 1**. Describe the character in **BIND 1**.
3. In **BIND 2**, match each active picture to its role.
4. Set **CHOOSE SHEET** to **0-6**. Start with **0: five panels + full body**.
5. Run. Inspect identity, profile, framing and clothing before keeping a sheet.

Read left to right. The seven editable sheet descriptions are below the main flow.
“Single image” means one output image; you can supply 1-9 references.

## Binding model - pictures are not subjects or output panels

### Three different numbers
**Subject 1** = the ONE character being depicted, even across many panels.

**Picture 1-9** = the active uploaded reference images in list order.

**Sheet index 0-6** = the desired output layout. It does not choose a reference.

`H3Subjects → H3RefSlots → H3ImagePromptCompose`

Identity + picture roles + ONE raw sheet description become ONE structured H3 prompt. The final prompt connects directly to conditioning and its preview.

## Dependencies - all custom nodes

### Install, then restart ComfyUI
- [H3 Character Sheets](https://github.com/Jalen-Brunson/ComfyUI-H3-Character-Sheets): Subjects, Ref Slots, Image Prompt Compose.
- [MMH3Tools](https://github.com/ckinpdx/ComfyUI-MMH3Tools): image list, reference conditioning, condition selector.
- [H3 Hybrid Loader](https://github.com/scottmudge/ComfyUI_MinimaxH3HybridLoader).
- [Fizgig H3 Still](https://github.com/shootthesound/ComfyUI-Fizgig-H3-Still): still latent + decode.
- [Easy Use](https://github.com/yolain/ComfyUI-Easy-Use): Any Index Switch.

Use current ComfyUI with native H3, Resolution Selector and Text (Multiline). No private helper node, VLM model or separate still VAE is required.

## Models - public downloads

### Select the files installed on your machine
[Comfy-Org / MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main): FL2VA + Ref2VA diffusion models, H3 Qwen text encoder, video VAE and audio VAE.

[Kijai / MiniMax-H3-experimental](https://huggingface.co/Kijai/MiniMax-H3-experimental/tree/main/loras): DMAD 4-step full LoRA (rank 39 bf16).

The README has exact filenames and folders. No weights or personal reference images are included. Upload placeholders must be replaced before running.

### Recipe
2.5 MP / 21:9 / multiple 32; ER-SDE, simple, 5-25 steps, denoise 1; CFG 1; DMAD 0.8; sigma shift 16 / 2; hybrid AdaLN blocks 25-49; seed 42.

Select the downloadable **stock Ref2VA overlay**. 

## 01 - choose and load reference images

### Reference input checklist
Use clear, sharp pictures of the same character. A neutral front view is a useful primary face source; add a true profile if needed. Include an outfit/body reference when those details matter.

**Picture 1 is enabled. Pictures 2-9 start bypassed.** Upload the next picture, then right-click its node → Mode → Always (or Ctrl+B). Set its matching `pic_N` role in BIND 2.

Enable consecutive slots **1 through N**. Bypassing or disconnecting a middle slot compresses the image list and renumbers later pictures. Move images and update their roles together.

Do not feed the same picture into two slots by accident. Each uploaded image is one picture even if it contains multiple panels.

## When an input is already a character sheet

Use **face sheet** for a multi-view face-only reference; use **character sheet** for a sheet containing face, hair, outfit and body information. Use **face (primary)** for a single face photo where you want to lock that face as the primary.


## 02 - prompt binding instructions

### BIND 1: who is being drawn?
Edit `subject1_description`: age range, face, hair, build and clothing. Keep Subjects 2 and 3 empty for this single-character workflow. All panels show Subject 1.

`subject1_position` is a textual alias, not panel placement. `subject1_lora` is only a trigger token: it does NOT load a LoRA. Leave it empty unless you add a character LoRA. The DMAD LoRA is a speed adapter, not an identity token.

Set `setting` to the desired backdrop. Leave loop_tail = latent_anchor and setting_as_subject = false. Extra rules are optional global constraints.

### BIND 2: what should each picture contribute?
`pic_N` selects the role; `pic_N_for = subject 1` selects the character. Match N to the active image-list order. Several pictures can belong to Subject 1.

Example: Picture 1 = face (primary); Picture 2 = hair; Picture 3 = outfit. Enable exactly those three loaders. Set every other pic_N to unused; leave all video/audio roles unused.

## Roles, unused inputs, and diagnosis

**face (primary)**: main face identity. **face**: supporting face angle. **face + hair**: both from one photo. **hair**: hairstyle. **body**: build/proportions only. **outfit**: clothes. **appearance**: overall look except face. **face sheet / character sheet**: a multi-view reference. **setting**: backdrop.

`pic_N_note` adds a qualifier such as “side profile”. Keep it short and factual.

**unused removes a text binding; it does not disable the uploaded image.** Also bypass the corresponding Load Image node, keeping active slots consecutive.

If the wrong face/outfit appears, compare the active image order with pic_N roles and inspect the final prompt. If panels are wrong, edit the selected raw template below. Never paste an already composed H3 prompt into a template.

## 03 - choose the output character sheet

### CHOOSE SHEET uses a zero-based index
| Index | Output | Choose it for |
| --- | --- | --- |
| **0** | 5 panels: four faces + full body | General-purpose reference; start here |
| **1** | 7 panels: six faces + full body | Angles, smile/anger/sadness, and outfit |
| **2** | 6 headshots, 2 × 3 | Face identity and expression coverage |
| **3** | 5 panels: four faces + neck-to-feet | Larger body/clothing detail |
| **4** | 2 headshots: front + profile | Simple likeness/profile check |
| **5** | 3 columns: front + profile + body crop | Large views in one ultrawide row |
| **6** | Free text (starts as one portrait) | A custom composition or quick portrait |

Only the selected description is used. Edit its matching numbered text node below. Values 7-9 have no template; use 0-6.

The saved canvas is 21:9. Try 3:2 for six heads, 2:3 for one portrait; keep 21:9 for the three-column template. Changing the index does NOT change resolution.

## 04 - model setup

Put the two diffusion checkpoints in `models/diffusion_models`, the H3 encoder in `models/text_encoders`, and both VAEs in `models/vae`. Put DMAD in `models/loras/minimax` to match the saved selection, or select its installed path.

Hybrid: FL2VA base, Ref2VA overlay, block_range_adaln 25-49, final AdaLN from base. CLIP type must be **minimax**.

The video VAE serves both reference encoding and Fizgig decode. The audio VAE is connected because the H3 conditioning node requires it; no audio is saved.

Start with the saved sampler/LoRA settings. The “4step” filename does not require changing this saved still recipe to four steps.

## 05 - conditioning only

The selected prompt and ordered images enter H3 reference conditioning.

Keep **total_frames = 5** and condition index **0**. This node's latent output is intentionally unused: **Fizgig Still Latent** supplies the sampler's true one-frame latent.

Width and height come from the SAME Resolution Selector. Keep the multiple at **32**. Never wire the conditioning node's clip latent into the sampler for this still workflow.

## 06 - sampling controls

The seed is fixed at **42** so comparisons are repeatable. Change it or choose randomize for variations.

**25 steps / ER-SDE / simple / denoise 1** are inherited from the source. BasicGuider gives CFG 1. Fizgig batch_size = 1 produces one sheet.

More output pixels give each panel more room; more panels divide that same canvas into smaller views. Reduce reference count or resolution if memory is tight.

## 07 - choose a good generated sheet

Before reusing a result, check EVERY panel:
- Same face, hairline, skin tone, clothing and jewelry.
- Requested panel count and order; no duplicate figures.
- Profile is a true 90-degree view with the far eye hidden.
- Full hairstyle fits in headshots; hands and feet fit in body views.
- Similar head size and lighting across the headshots.
- The neck-to-feet crop is intentional only for options 3 and 5.

Try another seed if a panel drifts. A simpler 2- or 3-view sheet can be more useful than a crowded sheet with inconsistent identity.

## Output and prompt troubleshooting

PNG files are written beneath `ComfyUI/output/h3_character_sheets/` and shown in Save Image. The saved PNG includes workflow metadata.

Inspect **Final H3 prompt** after a run. Expect one subject_definitions section and one detailed_description section, with Picture tags matching your active inputs.

Missing nodes: install all five packs and restart ComfyUI. Missing model: select an installed filename. Missing image: upload Picture 1 and every enabled optional image. Wrong layout: check sheet index 0-6 and the corresponding template.

Use plain text in descriptions. Avoid literal pipe characters: MMH3Tools treats a pipe as a separator between multiple prompts.

## Exact model files

Download the following from [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main), preserving the indicated ComfyUI model folders:

| Folder under `ComfyUI/models` | File |
| --- | --- |
| `diffusion_models` | `minimax_h3_fl2va_int8_convrot.safetensors` |
| `diffusion_models` | `minimax_h3_ref2va_int8_convrot.safetensors` |
| `text_encoders` | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` |
| `vae` | `minimax_h3_video_vae_int8_convrot.safetensors` |
| `vae` | `minimax_h3_audio_vae_fp32.safetensors` |

Download [DMAD rank 39 bf16](https://huggingface.co/Kijai/MiniMax-H3-experimental/blob/main/loras/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors) into `ComfyUI/models/loras/minimax/`. 

