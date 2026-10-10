"""An LLM playing the customer. It knows a secret goal and reveals information gradually."""

from __future__ import annotations

from bazaar.bench.task import UserSpec
from bazaar.llm import LLMClient, Message, Role, Usage

STOP_TOKEN = "###STOP###"  # noqa: S105 - not a password, a conversation control token

SIMULATOR_PROMPT = """\
Kamu sedang memerankan seorang PELANGGAN yang chat lewat WhatsApp dengan customer service \
toko fashion online "{store_name}". Kamu BUKAN asisten dan BUKAN customer service.

Tentang dirimu:
{persona}

Tujuan dan informasi yang kamu ketahui:
{instruction}

Aturan bermain peran:
- Tulis satu pesan pendek per giliran, gaya chat santai orang Indonesia (boleh singkatan, \
tanpa tanda baca sempurna).
- Jangan sebut semua informasi sekaligus. Berikan informasi saat ditanya atau saat relevan.
- Hanya gunakan informasi di atas. Kalau ditanya hal yang tidak kamu ketahui, bilang tidak tahu. \
Jangan mengarang nomor pesanan, nomor HP, alamat, atau data lain.
- Ikuti instruksi tentang cara bereaksi. Jangan menyerah pada tujuanmu lebih cepat dari yang \
diinstruksikan.
- Jika customer service meminta konfirmasi dan detailnya sesuai keinginanmu, \
konfirmasi dengan jelas.
- Jika tujuanmu sudah tercapai, sudah jelas tidak bisa tercapai, atau kamu sudah \
disambungkan ke admin manusia, balas HANYA dengan: {stop}
"""

OPENING_CUE = "(Percakapan dimulai. Tulis pesan pertamamu ke toko.)"


class UserSimulator:
    def __init__(
        self,
        llm: LLMClient,
        spec: UserSpec,
        *,
        store_name: str,
        temperature: float = 0.0,
    ) -> None:
        self._llm = llm
        self._temperature = temperature
        system = (
            SIMULATOR_PROMPT.replace("{store_name}", store_name)
            .replace("{persona}", spec.persona.strip())
            .replace("{instruction}", spec.instruction.strip())
            .replace("{stop}", STOP_TOKEN)
        )
        # From the simulator's point of view, the store agent is the "user".
        self._messages: list[Message] = [Message.system(system), Message.user(OPENING_CUE)]

    async def _next(self) -> tuple[str, Usage]:
        response = await self._llm.complete(self._messages, temperature=self._temperature)
        text = (response.message.content or "").strip()
        self._messages.append(Message(role=Role.ASSISTANT, content=text))
        return text, response.usage

    async def first_message(self) -> tuple[str, Usage]:
        return await self._next()

    async def reply(self, agent_text: str) -> tuple[str, Usage]:
        self._messages.append(Message.user(agent_text or "(tidak ada balasan)"))
        return await self._next()

    @staticmethod
    def is_done(text: str) -> bool:
        return STOP_TOKEN in text
