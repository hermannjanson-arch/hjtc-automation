# -*- coding: utf-8 -*-
"""
description_template.py

Builds the standardized "grading label" style eBay description in English.
Only two things vary per listing:
  - item_title      -> shown in the header banner (pass the eBay listing title,
                        or a shortened version of it)
  - intro_paragraphs -> list[str], the free-text intro block extracted from
                        the OLD description (series name, set name etc.)
  - condition_paragraphs -> list[str], the free-text condition block extracted
                        from the OLD description (grade, flaws, notes)

Everything else (packaging, shipping, customs, footer...) is fixed and
identical across all listings, so it only has to be maintained in ONE place.
"""

from html import escape

NAVY = "#1B2333"
GOLD = "#B08D57"
BURGUNDY = "#7A1F2B"
IVORY = "#FAF7F0"
LINE = "#E4DDCB"
INK = "#2A2A28"
MUTED = "#6B675F"


def _p_block(paragraphs, size="15px", color=INK):
    """Turn a list of plain-text lines into styled <p> tags."""
    if not paragraphs:
        return ""
    out = []
    for line in paragraphs:
        line = escape(line.strip())
        if not line:
            continue
        out.append(
            f'<p style="font-size:{size};line-height:1.65;color:{color};margin:0 0 10px 0;">{line}</p>'
        )
    # remove bottom margin on last paragraph
    if out:
        out[-1] = out[-1].replace("margin:0 0 10px 0;", "margin:0;")
    return "\n".join(out)


def build_description(item_title, condition_paragraphs):
    """
    item_title: str -> e.g. "Harry Potter Kakawow Cosmos - Albus Dumbledore 05/10"
    condition_paragraphs: list[str] -> extracted condition text from the old listing
                           (grade sentence + standard note + optional flaw sentence)
    """

    condition_html = _p_block(condition_paragraphs, size="14px")
    title_escaped = escape(item_title.strip())

    return f"""<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:680px;margin:0 auto;background-color:{IVORY};font-family:Georgia,'Times New Roman',serif;border:1px solid {LINE};">

  <!-- HEADER -->
  <tr>
    <td bgcolor="{NAVY}" style="background-color:{NAVY};padding:26px 24px 22px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-family:'Courier New',Courier,monospace;font-size:11px;letter-spacing:3px;color:{GOLD};text-transform:uppercase;padding-bottom:8px;">
            Trading Card &middot; Collectible
          </td>
        </tr>
        <tr>
          <td style="font-family:Georgia,'Times New Roman',serif;font-size:24px;line-height:1.3;color:{IVORY};font-weight:bold;">
            {title_escaped}
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- CONDITION (variable) -->
  <tr>
    <td style="padding:22px 24px 0 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-left:4px solid {BURGUNDY};background-color:#FFFFFF;">
        <tr>
          <td style="padding:16px 18px;">
            <div style="font-family:'Courier New',Courier,monospace;font-size:11px;letter-spacing:2px;color:{BURGUNDY};text-transform:uppercase;margin-bottom:8px;">
              Condition
            </div>
            {condition_html}
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- SHIPPING (fixed) -->
  <tr>
    <td style="padding:26px 24px 0 24px;">
      <div style="font-family:Georgia,serif;font-size:18px;color:{NAVY};font-weight:bold;border-bottom:2px solid {LINE};padding-bottom:8px;">
        Shipping &ndash; Domestic &amp; International
      </div>
    </td>
  </tr>
  <tr>
    <td style="padding:14px 24px 0 24px;">
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0 0 12px 0;">
        We ship from Germany to most countries worldwide, including the European Union, the United States,
        the United Kingdom, Canada, Asia, and Australia.
      </p>
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0 0 12px 0;">
        Within Germany, we ship via Deutsche Post with tracking available upon request. For international
        orders, we ship via DHL International, UPS, or the SPEED-PAK shipping program. Combined shipping is
        only possible <strong>before</strong> completing payment &ndash; please contact us first. For single
        cards, each additional item adds &euro;1 to shipping; for lots, combined shipping cost may vary.
      </p>
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0;">
        Shipping costs vary based on order size, packaging method, and destination. Single cards or small
        lots are typically inexpensive; larger or insured packages may cost more.
      </p>
    </td>
  </tr>

  <!-- HIGH VALUE SHIPPING (fixed, highlighted) -->
  <tr>
    <td style="padding:22px 24px 0 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{NAVY};">
        <tr>
          <td style="padding:18px 20px;">
            <div style="font-family:'Courier New',Courier,monospace;font-size:11px;letter-spacing:2px;color:{GOLD};text-transform:uppercase;margin-bottom:8px;">
              High-Value Shipping &middot; over &euro;250
            </div>
            <p style="font-size:14px;line-height:1.7;color:{IVORY};margin:0 0 10px 0;">
              For high-value items we strongly recommend tracked and insured shipping. Orders exceeding
              &euro;250 are automatically shipped via a fully insured, tracked service (DHL within the EU;
              typically UPS or DHL internationally).
            </p>
            <p style="font-size:14px;line-height:1.7;color:{IVORY};margin:0;">
              For orders under &euro;250, insurance is optional within the EU (but recommended). For
              deliveries outside the EU, SPEED-PAK shipments include insurance up to &euro;100.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- CUSTOMS (fixed) -->
  <tr>
    <td style="padding:26px 24px 0 24px;">
      <div style="font-family:Georgia,serif;font-size:18px;color:{NAVY};font-weight:bold;border-bottom:2px solid {LINE};padding-bottom:8px;">
        Customs &amp; Import Duties
      </div>
    </td>
  </tr>
  <tr>
    <td style="padding:14px 24px 0 24px;">
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0 0 10px 0;">
        We suggest declaring the actual item value to your local customs authority. Buyers are responsible
        for any <strong>import duties, VAT, or local taxes</strong>.
      </p>
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0;">
        In some countries (e.g. UK, Australia), eBay may collect import VAT at checkout &ndash; please check
        your local eBay policy.
      </p>
    </td>
  </tr>

  <!-- AUCTION & PAYMENT (fixed) -->
  <tr>
    <td style="padding:26px 24px 0 24px;">
      <div style="font-family:Georgia,serif;font-size:18px;color:{NAVY};font-weight:bold;border-bottom:2px solid {LINE};padding-bottom:8px;">
        Auction &amp; Payment
      </div>
    </td>
  </tr>
  <tr>
    <td style="padding:14px 24px 0 24px;">
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0 0 10px 0;">
        For auction listings, payment is due within <strong>4 days</strong> of the auction ending.
      </p>
      <p style="font-size:14px;line-height:1.7;color:{INK};margin:0;">
        Orders that remain unpaid after 4 days will be cancelled.
      </p>
    </td>
  </tr>

  <!-- PLEASE READ (fixed) -->
  <tr>
    <td style="padding:26px 24px 0 24px;">
      <div style="font-family:Georgia,serif;font-size:18px;color:{NAVY};font-weight:bold;border-bottom:2px solid {LINE};padding-bottom:8px;">
        Please Read Before Purchase
      </div>
    </td>
  </tr>
  <tr>
    <td style="padding:16px 24px 0 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td width="22" valign="top" style="font-family:'Courier New',Courier,monospace;color:{BURGUNDY};font-size:14px;padding:5px 0;">&#10003;</td>
          <td valign="top" style="font-size:14px;line-height:1.6;color:{INK};padding:5px 0;">The card in the photos is exactly what you will receive.</td>
        </tr>
        <tr>
          <td width="22" valign="top" style="font-family:'Courier New',Courier,monospace;color:{BURGUNDY};font-size:14px;padding:5px 0;">&#10003;</td>
          <td valign="top" style="font-size:14px;line-height:1.6;color:{INK};padding:5px 0;">For large lots or full sets, individual card photos may not be shown &ndash; just ask if needed.</td>
        </tr>
        <tr>
          <td width="22" valign="top" style="font-family:'Courier New',Courier,monospace;color:{BURGUNDY};font-size:14px;padding:5px 0;">&#10003;</td>
          <td valign="top" style="font-size:14px;line-height:1.6;color:{INK};padding:5px 0;">Small imperfections may occur from production or handling &ndash; please check the photos closely.</td>
        </tr>
        <tr>
          <td width="22" valign="top" style="font-family:'Courier New',Courier,monospace;color:{BURGUNDY};font-size:14px;padding:5px 0;">&#10003;</td>
          <td valign="top" style="font-size:14px;line-height:1.6;color:{INK};padding:5px 0;">Returns are accepted in accordance with EU consumer protection law. International untracked shipments are not refundable in case of loss. Questions about shipping or insurance? Contact us before you buy.</td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- FOOTER (fixed) -->
  <tr>
    <td style="padding:26px 24px 26px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid {LINE};">
        <tr>
          <td style="padding-top:16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.7;color:{MUTED};">
            Commercial sale &ndash; small business under &sect;19 UStG (Germany).<br>
            No VAT is shown or charged.
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
"""
