"""Geração do payload Pix (BR Code / EMV) e QR code para pagamento manual.

Usado na tela pós-cadastro (/verificar) enquanto não há gateway de cobrança
recorrente integrado — o usuário paga via Pix Copia-e-Cola/QR code e envia o
comprovante por WhatsApp para liberação manual do acesso.
"""
import segno

PIX_CHAVE = "b4e890c5-d9ad-4e0a-9dcb-7f78d6b888aa"
PIX_NOME = "MARCIANO LUIS CADORE"
PIX_CIDADE = "PASSO FUNDO"
PIX_VALOR = "24.99"


def _tlv(id_str: str, value: str) -> str:
    return f"{id_str}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    """CRC16-CCITT (poly 0x1021, init 0xFFFF), exigido pelo padrão BR Code."""
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def gerar_payload_pix() -> str:
    """Monta a string "Pix Copia e Cola" (BR Code estático, reutilizável)."""
    conta = _tlv("00", "br.gov.bcb.pix") + _tlv("01", PIX_CHAVE)
    dados_adicionais = _tlv("05", "***")

    sem_crc = (
        _tlv("00", "01")           # Payload Format Indicator
        + _tlv("01", "11")         # Point of Initiation Method: 11 = reutilizável
        + _tlv("26", conta)        # Merchant Account Information (Pix)
        + _tlv("52", "0000")       # Merchant Category Code
        + _tlv("53", "986")        # Transaction Currency: BRL
        + _tlv("54", PIX_VALOR)    # Transaction Amount
        + _tlv("58", "BR")         # Country Code
        + _tlv("59", PIX_NOME)     # Merchant Name
        + _tlv("60", PIX_CIDADE)   # Merchant City
        + _tlv("62", dados_adicionais)
        + "6304"
    )
    return sem_crc + _crc16_ccitt(sem_crc)


def gerar_qrcode_svg() -> str:
    """Gera o QR code do payload Pix como SVG inline (sem dependências pesadas)."""
    qr = segno.make(gerar_payload_pix(), error="m")
    return qr.svg_inline(scale=8, border=2, dark="#0a1712", light="#ffffff")


PIX_PAYLOAD = gerar_payload_pix()
PIX_QRCODE_SVG = None


def get_qrcode_svg() -> str:
    global PIX_QRCODE_SVG
    if PIX_QRCODE_SVG is None:
        PIX_QRCODE_SVG = gerar_qrcode_svg()
    return PIX_QRCODE_SVG
