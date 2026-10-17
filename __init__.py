from .nodes import H3Subjects, H3RefSlots, H3ImagePromptCompose

NODE_CLASS_MAPPINGS = {
    "H3Subjects": H3Subjects,
    "H3RefSlots": H3RefSlots,
    "H3ImagePromptCompose": H3ImagePromptCompose,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3Subjects": "H3 Subjects (builder)",
    "H3RefSlots": "H3 Ref Slots (builder)",
    "H3ImagePromptCompose": "H3 Image Prompt Compose",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
