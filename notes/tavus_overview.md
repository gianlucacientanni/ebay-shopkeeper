# Pals
PAL stands for Personified Application Layer. A PAL is what you build, it has a Face (how it looks), a Voice (how it sounds) as well as the pipelines, tools and interfaces available to it to shape how it behaves.

You build a PAL through CVI (Conversational Video Interface), this is a framework for creating real-time multimodal interactions with AI. CVI is what allows for low latency AI face reactions to input. There are 3 pillars around which CVI is built:
1) PAL
2) Face
3) Conversation (the real-time video session between the user and Tavus avatar)

# CVI

CVI is built on a modular layer system, where each layer handles a specific part of the interaction:

- Perception (Raven)
- Conversational flow (Sparrow)
- Speech recognition
- LLM
- TTS
- Realtime face (Pheonix)

Most of these layers are configurable via the PAL. 