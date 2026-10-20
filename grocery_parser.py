# import json
# import re
# import unicodedata
# from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# from llama_cpp import Llama


# MODEL_PATH = (
#     "/home/hari/voicesearch_ai/models/"
#     "Qwen3-1.7B-Q4_K_M.gguf"
# )


# Quantity = Optional[Union[int, float]]
# Span = Tuple[int, int]


# # =============================================================================
# # PASS 1 — TOKEN SEMANTICS ONLY
# # =============================================================================
# #
# # This stage does NOT decide product boundaries and does NOT create product
# # names. It only decides whether every transcript token is:
# #
# #   number    -> spoken numeric expression / fraction / count
# #   unit      -> explicitly spoken measurement/package/count unit
# #   word      -> ordinary lexical word (normally part of a product name)
# #   separator -> connector/filler/punctuation-like speech token
# #
# # Two independent passes are run. If they disagree, a focused tie-break call
# # decides that exact token in context.
# #
# # This is deliberately much simpler than asking one small model to decide
# # products + boundaries + quantities + units at the same time.
# # =============================================================================

# TOKEN_ROLE_PROMPT_A = r"""
# You are a TOKEN SEMANTICS classifier for grocery voice search.

# The customer may speak:
# - Tamil
# - colloquial/regional Tamil
# - imperfect ASR Tamil
# - Tanglish
# - English
# - mixed Tamil/English
# - digits

# You receive the ORIGINAL transcript and numbered whitespace tokens.

# For EVERY token index exactly once, assign ONE role:

# "number"
#     The token itself is a spoken numeric expression or part of a multi-token
#     numeric expression. This includes colloquial/formal Tamil number words,
#     Tanglish/English number words, digits, fractions and imperfect-ASR forms
#     that clearly represent a number in context.

# "unit"
#     The token itself explicitly expresses a measurement/package/count unit:
#     weight, volume, packet, bottle, piece/count, box, dozen, etc.

# "word"
#     An ordinary lexical word. In this grocery-search context it is normally a
#     product-name word.

# "separator"
#     Only a connector/filler/separator, not a product word, number, or unit.

# IMPORTANT:
# - Classify the TOKEN, not an arbitrary phrase around it.
# - Never absorb the next product word into a number.
# - Never absorb a number into a product.
# - A product may have no quantity.
# - Product words may be adjacent with no pause or "and".
# - A real multi-word product is still multiple "word" tokens at this stage.
# - Do NOT decide whether adjacent product words belong together yet.
# - Do NOT translate, correct, or invent transcript text.
# - Return EVERY token index exactly once.

# Example principle:
# tokens:
# 0: chicken
# 1: masala
# 2: fifty
# 3: peas
# 4: two-hundred

# roles:
# 0 word
# 1 word
# 2 number
# 3 word
# 4 number

# Return JSON only:
# {
#   "tokens": [
#     {"index": 0, "role": "word"}
#   ]
# }

# /no_think
# """


# TOKEN_ROLE_PROMPT_B = r"""
# Independently classify EVERY numbered transcript token for grocery voice search.

# Allowed roles:
# - number
# - unit
# - word
# - separator

# NUMBER:
# A spoken number, count, fraction, compound-number component, digit, or an
# imperfect-ASR token that clearly means a number in this sentence.

# UNIT:
# An explicitly spoken measurement/package/count unit only.

# WORD:
# A normal lexical word, usually a product-name word.

# SEPARATOR:
# Only a connector/filler.

# STRICT RULES:
# 1. Return one record for every token index.
# 2. Never classify a normal product word as part of the previous number.
# 3. Never classify a number word as a grocery product word.
# 4. Multi-word product names are NOT joined here. Their tokens remain "word".
# 5. Do not require digits; spoken Tamil number words are numbers.
# 6. Understand colloquial/regional Tamil and plausible ASR corruption
#    semantically from context.
# 7. Do not translate or rewrite anything.

# Return JSON only:
# {
#   "tokens": [
#     {"index": 0, "role": "word"}
#   ]
# }

# /no_think
# """


# TOKEN_TIE_BREAK_PROMPT = r"""
# You are resolving ONE disputed transcript token.

# Choose exactly one role:
# - number
# - unit
# - word
# - separator

# Use the ORIGINAL transcript and local context.

# Important:
# - "number" means the token itself expresses a numeric value/fraction/count or
#   is clearly an imperfect-ASR number form.
# - "unit" means the token itself is an explicitly spoken measurement/package
#   unit.
# - "word" means an ordinary lexical/product-name word.
# - Do not let a nearby number swallow a product word.
# - Do not turn a number word into a product.
# - Do not translate/correct the token.

# Return JSON only:
# {
#   "role": "number"
# }

# /no_think
# """


# # =============================================================================
# # PASS 2 — PRODUCT BOUNDARIES ONLY
# # =============================================================================
# #
# # At this point number/unit tokens are already removed from product coverage.
# # We only ask whether directly adjacent WORD tokens belong to one natural
# # product name or two separate products.
# # =============================================================================

# BOUNDARY_PROMPT_A = r"""
# You decide PRODUCT BOUNDARIES between adjacent product-word tokens.

# The transcript is grocery voice search and may contain Tamil, colloquial Tamil,
# Tanglish, English, mixed speech, and imperfect ASR.

# You receive candidate adjacent WORD pairs. For every pair return:

# "same_product"
#     only when the two adjacent words naturally belong to ONE purchasable
#     product name in this context.

# "new_product"
#     when the right word starts another requested product.

# Examples of principle:
# - a spice/product compound such as "chicken masala" can be one product
# - two separately purchasable grocery items spoken continuously are separate

# IMPORTANT:
# - Customers do NOT need pauses, commas, or "and" between products.
# - Do not merge merely because words are adjacent.
# - Preserve genuine multi-word product names.
# - Judge only the supplied pair in the full transcript context.
# - Return every pair id exactly once.

# Return JSON only:
# {
#   "boundaries": [
#     {"pair_id": 0, "relation": "same_product"}
#   ]
# }

# /no_think
# """


# BOUNDARY_PROMPT_B = r"""
# Independently audit adjacent grocery product-word pairs.

# For each supplied pair choose exactly:
# - same_product
# - new_product

# Use SAME_PRODUCT only if the two words clearly form one natural purchasable
# product name in the sentence.

# Otherwise choose NEW_PRODUCT.

# There may be several products spoken continuously without pauses or connector
# words. Adjacency alone never proves one product.

# Do not translate, correct, or invent product words.

# Return every pair id exactly once as JSON:
# {
#   "boundaries": [
#     {"pair_id": 0, "relation": "new_product"}
#   ]
# }

# /no_think
# """


# BOUNDARY_FINAL_VERIFY_PROMPT = r"""
# You are the FINAL verifier for ONE proposed grocery product merge.

# The first two boundary classifiers both proposed SAME_PRODUCT.

# You must independently decide whether the LEFT WORD and RIGHT WORD really
# belong to ONE purchasable product name in the ORIGINAL transcript.

# Return exactly one relation:

# "same_product"
#     Use this ONLY when the full two-word phrase is naturally one single
#     purchasable product name in this context.

# "new_product"
#     Use this when the two words are independently purchasable/requested
#     products spoken next to each other.

# Important:

# - Grocery customers often list separate products with no pause or connector.
# - Mere adjacency is never enough to merge.
# - Do not merge simply because both words are grocery-related.
# - Preserve genuine multi-word product names.
# - If both words can naturally be separate requested groceries and the phrase
#   is not clearly one established product name in context, choose new_product.
# - Do not use quantities or units as product words.
# - Do not translate, correct, or invent text.

# Return JSON only:

# {
#   "relation": "new_product"
# }

# /no_think
# """


# # =============================================================================
# # PASS 3 — SEMANTIC QUANTITY CONVERSION
# # =============================================================================

# MEASUREMENT_PARSE_PROMPT = r"""
# You convert already-identified SPOKEN QUANTITY PHRASES into numeric values.

# You receive measurement rows. Each row contains:
# - measurement_id
# - quantity_text: exact transcript number words
# - explicit_unit_text: exact explicitly spoken unit words, or empty

# For EVERY row:

# 1. Understand quantity_text SEMANTICALLY.
#    It may be:
#    - formal Tamil
#    - colloquial/regional Tamil
#    - imperfect ASR Tamil
#    - Tanglish
#    - English
#    - digits
#    - multi-token compound numbers
#    - fractions

# 2. Return the COMPLETE mathematical value as digits.
#    This is NOT a finite lookup-table task.

# 3. If explicit_unit_text is present:
#    normalize BOTH quantity and unit:
#    - kilograms / kg -> grams, unit "g"
#    - litres / liters / l -> millilitres, unit "ml"
#    - grams -> "g"
#    - ml -> "ml"
#    - package/count units -> packet, bottle, pcs, box, dozen as appropriate

# 4. If explicit_unit_text is empty:
#    return unit="unknown".
#    Unit inference happens later from the product meaning.

# 5. Do not invent a quantity.
# 6. Do not use nearby product words as part of quantity_text.

# Examples only illustrate semantics:
# - Tamil word meaning fifty -> quantity "50"
# - Tamil word meaning two hundred -> "200"
# - imperfect ASR number form that clearly means two hundred -> "200"
# - one litre -> quantity "1000", unit "ml"
# - half kilogram -> quantity "500", unit "g"

# Return every measurement_id exactly once.

# JSON only:
# {
#   "measurements": [
#     {
#       "measurement_id": 0,
#       "quantity": "50",
#       "unit": "unknown"
#     }
#   ]
# }

# /no_think
# """


# SINGLE_MEASUREMENT_PROMPT = r"""
# Convert this one spoken quantity expression semantically.

# Inputs:
# - quantity_text
# - explicit_unit_text (may be empty)

# The quantity may be Tamil, colloquial/regional Tamil, imperfect ASR Tamil,
# Tanglish, English, digits, compound numbers or fractions.

# Return the complete numeric value.

# If an explicit unit is present:
# - kg -> grams / g
# - litre/liter/l -> millilitres / ml
# - gram -> g
# - ml -> ml
# - explicit package/count -> packet/bottle/pcs/box/dozen as appropriate

# If no unit is explicitly spoken, return unit="unknown".

# Do not infer a product unit here.

# JSON only:
# {
#   "quantity": "50",
#   "unit": "unknown"
# }

# /no_think
# """


# # =============================================================================
# # PASS 4 — NATURAL UNIT INFERENCE
# # =============================================================================

# UNIT_INFERENCE_PROMPT = r"""
# You infer the NATURAL RETAIL MEASUREMENT UNIT for products whose customer
# spoke a quantity but DID NOT speak a unit.

# You receive:
# - product_index
# - product_name exactly as heard
# - numeric quantity already parsed

# For every row choose exactly one canonical unit:

# - g
# - ml
# - packet
# - bottle
# - pcs
# - box
# - dozen
# - unknown

# Use product semantics and normal grocery retail measurement.

# Examples of the principle:
# - dry groceries/spices/powders commonly measured by weight -> g
# - liquids commonly measured by volume -> ml
# - products naturally requested as packets -> packet
# - countable individual items -> pcs
# - products naturally requested as bottles -> bottle
# - boxed products -> box

# IMPORTANT:
# - There is NO hardcoded product-to-unit mapping.
# - Infer semantically from the product.
# - Do NOT change the customer's numeric quantity.
# - Use unknown only when genuinely ambiguous.
# - Do not translate or rename the product.

# Return every product_index exactly once.

# JSON only:
# {
#   "units": [
#     {"product_index": 0, "unit": "g"}
#   ]
# }

# /no_think
# """


# SINGLE_UNIT_INFERENCE_PROMPT = r"""
# Infer the natural retail measurement unit for this grocery/product.

# Allowed:
# g, ml, packet, bottle, pcs, box, dozen, unknown

# The customer supplied a numeric quantity but no explicit unit.
# Use product semantics and normal retail measurement.
# Do not change the quantity.
# Do not translate or rename the product.
# Use unknown only when genuinely ambiguous.

# JSON only:
# {
#   "unit": "g"
# }

# /no_think
# """


# class GroceryParser:
#     def __init__(self) -> None:
#         print("Loading Qwen grocery parser...", flush=True)

#         self.llm = Llama(
#             model_path=MODEL_PATH,
#             n_ctx=4096,
#             n_threads=4,
#             n_batch=128,
#             verbose=False,
#             seed=42,
#         )

#         print("Qwen grocery parser ready.", flush=True)

#     # =========================================================================
#     # BASIC HELPERS
#     # =========================================================================

#     @staticmethod
#     def _normalize_text(value: Any) -> str:
#         text = unicodedata.normalize(
#             "NFKC",
#             str(value or ""),
#         )

#         text = re.sub(
#             r"[,;|\u3001]+",
#             " ",
#             text,
#         )

#         text = re.sub(
#             r"\s+",
#             " ",
#             text,
#         ).strip()

#         return text

#     @classmethod
#     def _tokenize(cls, transcript: str) -> List[str]:
#         text = cls._normalize_text(transcript)

#         if not text:
#             return []

#         return text.split()

#     @staticmethod
#     def _tokens_for_prompt(tokens: Sequence[str]) -> str:
#         return "\n".join(
#             f"{index}: {token}"
#             for index, token in enumerate(tokens)
#         )

#     @staticmethod
#     def _parse_quantity(value: Any) -> Quantity:
#         text = str(value or "").strip()

#         if not text:
#             return None

#         if not re.fullmatch(
#             r"\d+(?:\.\d+)?",
#             text,
#         ):
#             return None

#         number = float(text)

#         if number <= 0:
#             return None

#         if number.is_integer():
#             return int(number)

#         return number

#     @staticmethod
#     def _normalize_unit(value: Any) -> str:
#         unit = str(
#             value or "unknown"
#         ).strip().lower()

#         aliases = {
#             "": "unknown",
#             "unknown": "unknown",

#             "g": "g",
#             "gm": "g",
#             "gms": "g",
#             "gram": "g",
#             "grams": "g",

#             "ml": "ml",
#             "millilitre": "ml",
#             "millilitres": "ml",
#             "milliliter": "ml",
#             "milliliters": "ml",

#             "packet": "packet",
#             "packets": "packet",
#             "pack": "packet",
#             "packs": "packet",
#             "pkt": "packet",

#             "bottle": "bottle",
#             "bottles": "bottle",

#             "pc": "pcs",
#             "pcs": "pcs",
#             "piece": "pcs",
#             "pieces": "pcs",
#             "count": "pcs",

#             "box": "box",
#             "boxes": "box",

#             "dozen": "dozen",
#         }

#         return aliases.get(
#             unit,
#             "unknown",
#         )

#     # =========================================================================
#     # JSON SCHEMAS
#     # =========================================================================

#     @staticmethod
#     def _token_roles_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "tokens": {
#                     "type": "array",
#                     "items": {
#                         "type": "object",
#                         "properties": {
#                             "index": {
#                                 "type": "integer",
#                             },
#                             "role": {
#                                 "type": "string",
#                             },
#                         },
#                         "required": [
#                             "index",
#                             "role",
#                         ],
#                     },
#                 },
#             },
#             "required": [
#                 "tokens",
#             ],
#         }

#     @staticmethod
#     def _single_role_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "role": {
#                     "type": "string",
#                 },
#             },
#             "required": [
#                 "role",
#             ],
#         }

#     @staticmethod
#     def _boundary_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "boundaries": {
#                     "type": "array",
#                     "items": {
#                         "type": "object",
#                         "properties": {
#                             "pair_id": {
#                                 "type": "integer",
#                             },
#                             "relation": {
#                                 "type": "string",
#                             },
#                         },
#                         "required": [
#                             "pair_id",
#                             "relation",
#                         ],
#                     },
#                 },
#             },
#             "required": [
#                 "boundaries",
#             ],
#         }

#     @staticmethod
#     def _single_boundary_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "relation": {
#                     "type": "string",
#                 },
#             },
#             "required": [
#                 "relation",
#             ],
#         }

#     @staticmethod
#     def _measurement_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "measurements": {
#                     "type": "array",
#                     "items": {
#                         "type": "object",
#                         "properties": {
#                             "measurement_id": {
#                                 "type": "integer",
#                             },
#                             "quantity": {
#                                 "type": "string",
#                             },
#                             "unit": {
#                                 "type": "string",
#                             },
#                         },
#                         "required": [
#                             "measurement_id",
#                             "quantity",
#                             "unit",
#                         ],
#                     },
#                 },
#             },
#             "required": [
#                 "measurements",
#             ],
#         }

#     @staticmethod
#     def _single_measurement_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "quantity": {
#                     "type": "string",
#                 },
#                 "unit": {
#                     "type": "string",
#                 },
#             },
#             "required": [
#                 "quantity",
#                 "unit",
#             ],
#         }

#     @staticmethod
#     def _unit_inference_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "units": {
#                     "type": "array",
#                     "items": {
#                         "type": "object",
#                         "properties": {
#                             "product_index": {
#                                 "type": "integer",
#                             },
#                             "unit": {
#                                 "type": "string",
#                             },
#                         },
#                         "required": [
#                             "product_index",
#                             "unit",
#                         ],
#                     },
#                 },
#             },
#             "required": [
#                 "units",
#             ],
#         }

#     @staticmethod
#     def _single_unit_schema() -> Dict[str, Any]:
#         return {
#             "type": "object",
#             "properties": {
#                 "unit": {
#                     "type": "string",
#                 },
#             },
#             "required": [
#                 "unit",
#             ],
#         }

#     # =========================================================================
#     # QWEN JSON CALL
#     # =========================================================================

#     def _call_json(
#         self,
#         messages: List[Dict[str, str]],
#         schema: Dict[str, Any],
#         max_tokens: int = 700,
#     ) -> Dict[str, Any]:
#         response = self.llm.create_chat_completion(
#             messages=messages,
#             response_format={
#                 "type": "json_object",
#                 "schema": schema,
#             },
#             temperature=0.0,
#             max_tokens=max_tokens,
#         )

#         content = (
#             response
#             .get(
#                 "choices",
#                 [{}],
#             )[0]
#             .get(
#                 "message",
#                 {},
#             )
#             .get(
#                 "content",
#                 "",
#             )
#         )

#         content = str(
#             content or ""
#         ).strip()

#         if not content:
#             raise RuntimeError(
#                 "Qwen returned an empty response"
#             )

#         result = json.loads(
#             content
#         )

#         if not isinstance(
#             result,
#             dict,
#         ):
#             raise RuntimeError(
#                 "Qwen JSON response was not an object"
#             )

#         return result

#     # =========================================================================
#     # TOKEN ROLE CLASSIFICATION
#     # =========================================================================

#     def _run_token_role_pass(
#         self,
#         prompt: str,
#         transcript: str,
#         tokens: Sequence[str],
#     ) -> Dict[int, str]:
#         result = self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content": prompt,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "ORIGINAL TRANSCRIPT:\n"
#                         f"{transcript}\n\n"
#                         "TOKENS:\n"
#                         f"{self._tokens_for_prompt(tokens)}\n\n"
#                         "Return one role for EVERY token index.\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             schema=self._token_roles_schema(),
#             max_tokens=max(
#                 450,
#                 len(tokens) * 45,
#             ),
#         )

#         valid_roles = {
#             "number",
#             "unit",
#             "word",
#             "separator",
#         }

#         role_map: Dict[int, str] = {}

#         raw_tokens = result.get(
#             "tokens",
#             [],
#         )

#         if not isinstance(
#             raw_tokens,
#             list,
#         ):
#             return role_map

#         for row in raw_tokens:
#             if not isinstance(
#                 row,
#                 dict,
#             ):
#                 continue

#             index = row.get(
#                 "index"
#             )

#             role = str(
#                 row.get(
#                     "role",
#                     "",
#                 )
#             ).strip().lower()

#             if (
#                 isinstance(index, bool)
#                 or
#                 not isinstance(index, int)
#                 or
#                 not (
#                     0
#                     <= index
#                     < len(tokens)
#                 )
#                 or
#                 role not in valid_roles
#             ):
#                 continue

#             if index not in role_map:
#                 role_map[
#                     index
#                 ] = role

#         return role_map

#     def _resolve_disputed_token_role(
#         self,
#         transcript: str,
#         tokens: Sequence[str],
#         index: int,
#         role_a: Optional[str],
#         role_b: Optional[str],
#     ) -> str:
#         left = max(
#             0,
#             index - 2,
#         )

#         right = min(
#             len(tokens),
#             index + 3,
#         )

#         context_lines = "\n".join(
#             f"{i}: {tokens[i]}"
#             for i in range(
#                 left,
#                 right,
#             )
#         )

#         result = self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content":
#                         TOKEN_TIE_BREAK_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "ORIGINAL TRANSCRIPT:\n"
#                         f"{transcript}\n\n"
#                         "LOCAL TOKENS:\n"
#                         f"{context_lines}\n\n"
#                         f"TARGET INDEX: {index}\n"
#                         f"TARGET TOKEN: {tokens[index]}\n"
#                         f"FIRST CLASSIFIER: {role_a}\n"
#                         f"SECOND CLASSIFIER: {role_b}\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             schema=self._single_role_schema(),
#             max_tokens=80,
#         )

#         role = str(
#             result.get(
#                 "role",
#                 "",
#             )
#         ).strip().lower()

#         if role in {
#             "number",
#             "unit",
#             "word",
#             "separator",
#         }:
#             return role

#         # Coverage-first fallback:
#         # never silently lose an unknown token.
#         return "word"

#     def _classify_token_roles(
#         self,
#         transcript: str,
#         tokens: Sequence[str],
#     ) -> Dict[int, str]:
#         try:
#             role_a = (
#                 self._run_token_role_pass(
#                     TOKEN_ROLE_PROMPT_A,
#                     transcript,
#                     tokens,
#                 )
#             )
#         except Exception as error:
#             print(
#                 "Token role pass A failed:",
#                 error,
#                 flush=True,
#             )
#             role_a = {}

#         try:
#             role_b = (
#                 self._run_token_role_pass(
#                     TOKEN_ROLE_PROMPT_B,
#                     transcript,
#                     tokens,
#                 )
#             )
#         except Exception as error:
#             print(
#                 "Token role pass B failed:",
#                 error,
#                 flush=True,
#             )
#             role_b = {}

#         print(
#             "TOKEN ROLE PASS A:",
#             role_a,
#             flush=True,
#         )

#         print(
#             "TOKEN ROLE PASS B:",
#             role_b,
#             flush=True,
#         )

#         final_roles: Dict[int, str] = {}

#         for index in range(
#             len(tokens)
#         ):
#             a = role_a.get(
#                 index
#             )

#             b = role_b.get(
#                 index
#             )

#             if (
#                 a is not None
#                 and
#                 a == b
#             ):
#                 final_roles[
#                     index
#                 ] = a

#                 continue

#             # If only one pass succeeded for this index,
#             # use that answer rather than discarding it.
#             if (
#                 a is not None
#                 and
#                 b is None
#             ):
#                 final_roles[
#                     index
#                 ] = a

#                 continue

#             if (
#                 b is not None
#                 and
#                 a is None
#             ):
#                 final_roles[
#                     index
#                 ] = b

#                 continue

#             # Both missing -> preserve coverage as ordinary word.
#             if (
#                 a is None
#                 and
#                 b is None
#             ):
#                 final_roles[
#                     index
#                 ] = "word"

#                 continue

#             try:
#                 final_roles[
#                     index
#                 ] = (
#                     self
#                     ._resolve_disputed_token_role(
#                         transcript=transcript,
#                         tokens=tokens,
#                         index=index,
#                         role_a=a,
#                         role_b=b,
#                     )
#                 )

#             except Exception as error:
#                 print(
#                     "Token role tie-break failed "
#                     f"for index {index}:",
#                     error,
#                     flush=True,
#                 )

#                 # Product coverage is safer than dropping the token.
#                 final_roles[
#                     index
#                 ] = "word"

#         return final_roles

#     # =========================================================================
#     # PRODUCT BOUNDARIES
#     # =========================================================================

#     @staticmethod
#     def _candidate_word_pairs(
#         tokens: Sequence[str],
#         roles: Dict[int, str],
#     ) -> List[Dict[str, Any]]:
#         pairs: List[
#             Dict[str, Any]
#         ] = []

#         pair_id = 0

#         for index in range(
#             len(tokens) - 1
#         ):
#             if (
#                 roles.get(index)
#                 == "word"
#                 and
#                 roles.get(index + 1)
#                 == "word"
#             ):
#                 pairs.append(
#                     {
#                         "pair_id":
#                             pair_id,

#                         "left_index":
#                             index,

#                         "right_index":
#                             index + 1,

#                         "left_word":
#                             tokens[index],

#                         "right_word":
#                             tokens[index + 1],
#                     }
#                 )

#                 pair_id += 1

#         return pairs

#     def _run_boundary_pass(
#         self,
#         prompt: str,
#         transcript: str,
#         pairs: Sequence[
#             Dict[str, Any]
#         ],
#     ) -> Dict[int, str]:
#         if not pairs:
#             return {}

#         pair_lines = "\n".join(
#             (
#                 f"pair_id={pair['pair_id']} | "
#                 f"{pair['left_index']}:{pair['left_word']} | "
#                 f"{pair['right_index']}:{pair['right_word']}"
#             )
#             for pair in pairs
#         )

#         result = self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content": prompt,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "ORIGINAL TRANSCRIPT:\n"
#                         f"{transcript}\n\n"
#                         "ADJACENT WORD PAIRS:\n"
#                         f"{pair_lines}\n\n"
#                         "Return every pair_id.\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             schema=self._boundary_schema(),
#             max_tokens=max(
#                 300,
#                 len(pairs) * 45,
#             ),
#         )

#         final: Dict[
#             int,
#             str,
#         ] = {}

#         raw = result.get(
#             "boundaries",
#             [],
#         )

#         if not isinstance(
#             raw,
#             list,
#         ):
#             return final

#         valid_pair_ids = {
#             int(
#                 pair[
#                     "pair_id"
#                 ]
#             )
#             for pair in pairs
#         }

#         for row in raw:
#             if not isinstance(
#                 row,
#                 dict,
#             ):
#                 continue

#             pair_id = row.get(
#                 "pair_id"
#             )

#             relation = str(
#                 row.get(
#                     "relation",
#                     "",
#                 )
#             ).strip().lower()

#             if (
#                 isinstance(pair_id, bool)
#                 or
#                 not isinstance(
#                     pair_id,
#                     int,
#                 )
#                 or
#                 pair_id
#                 not in valid_pair_ids
#                 or
#                 relation
#                 not in {
#                     "same_product",
#                     "new_product",
#                 }
#             ):
#                 continue

#             if pair_id not in final:
#                 final[
#                     pair_id
#                 ] = relation

#         return final

#     def _verify_same_product_pair(
#         self,
#         transcript: str,
#         pair: Dict[str, Any],
#     ) -> str:

#         result = self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content":
#                         BOUNDARY_FINAL_VERIFY_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "ORIGINAL TRANSCRIPT:\n"
#                         f"{transcript}\n\n"
#                         "PROPOSED MERGE:\n"
#                         f"LEFT INDEX: {pair['left_index']}\n"
#                         f"LEFT WORD: {pair['left_word']}\n"
#                         f"RIGHT INDEX: {pair['right_index']}\n"
#                         f"RIGHT WORD: {pair['right_word']}\n\n"
#                         "Decide only this boundary.\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             schema=self._single_boundary_schema(),
#             max_tokens=80,
#         )

#         relation = str(
#             result.get(
#                 "relation",
#                 "",
#             )
#         ).strip().lower()

#         if relation in {
#             "same_product",
#             "new_product",
#         }:
#             return relation

#         # Safety-first for product coverage:
#         # an uncertain merge must not swallow a separate product.
#         return "new_product"

#     def _resolve_product_boundaries(
#         self,
#         transcript: str,
#         tokens: Sequence[str],
#         roles: Dict[int, str],
#     ) -> Dict[int, str]:
#         pairs = (
#             self._candidate_word_pairs(
#                 tokens,
#                 roles,
#             )
#         )

#         if not pairs:
#             return {}

#         try:
#             pass_a = (
#                 self._run_boundary_pass(
#                     BOUNDARY_PROMPT_A,
#                     transcript,
#                     pairs,
#                 )
#             )
#         except Exception as error:
#             print(
#                 "Boundary pass A failed:",
#                 error,
#                 flush=True,
#             )
#             pass_a = {}

#         try:
#             pass_b = (
#                 self._run_boundary_pass(
#                     BOUNDARY_PROMPT_B,
#                     transcript,
#                     pairs,
#                 )
#             )
#         except Exception as error:
#             print(
#                 "Boundary pass B failed:",
#                 error,
#                 flush=True,
#             )
#             pass_b = {}

#         print(
#             "BOUNDARY PASS A:",
#             pass_a,
#             flush=True,
#         )

#         print(
#             "BOUNDARY PASS B:",
#             pass_b,
#             flush=True,
#         )

#         final: Dict[int, str] = {}

#         for pair in pairs:
#             pair_id = int(
#                 pair[
#                     "pair_id"
#                 ]
#             )

#             left_index = int(
#                 pair[
#                     "left_index"
#                 ]
#             )

#             a = pass_a.get(
#                 pair_id
#             )

#             b = pass_b.get(
#                 pair_id
#             )

#             # Never merge only because two small-model passes
#             # both said SAME_PRODUCT. A final focused verifier must
#             # independently confirm the exact pair.
#             proposed_merge = (
#                 a == "same_product"
#                 and
#                 b == "same_product"
#             )

#             if proposed_merge:

#                 try:

#                     verified_relation = (
#                         self._verify_same_product_pair(
#                             transcript=transcript,
#                             pair=pair,
#                         )
#                     )

#                     print(
#                         "BOUNDARY FINAL VERIFY:",
#                         {
#                             "left":
#                                 pair["left_word"],
#                             "right":
#                                 pair["right_word"],
#                             "relation":
#                                 verified_relation,
#                         },
#                         flush=True,
#                     )

#                     final[
#                         left_index
#                     ] = verified_relation

#                 except Exception as error:

#                     print(
#                         "Boundary final verification failed "
#                         f"for {pair['left_word']} | "
#                         f"{pair['right_word']}:",
#                         error,
#                         flush=True,
#                     )

#                     # Coverage is more important than an uncertain merge.
#                     final[
#                         left_index
#                     ] = "new_product"

#             else:

#                 # Any disagreement, missing answer, or explicit NEW_PRODUCT
#                 # is conservatively split.
#                 final[
#                     left_index
#                 ] = "new_product"

#         return final

#     @staticmethod
#     def _build_product_spans(
#         tokens: Sequence[str],
#         roles: Dict[int, str],
#         boundaries: Dict[int, str],
#     ) -> List[Span]:
#         word_indexes = [
#             index
#             for index in range(
#                 len(tokens)
#             )
#             if roles.get(
#                 index
#             ) == "word"
#         ]

#         if not word_indexes:
#             return []

#         spans: List[
#             Span
#         ] = []

#         start = word_indexes[0]
#         previous = word_indexes[0]

#         for index in word_indexes[1:]:
#             # A number/unit/separator gap always separates products.
#             if index != previous + 1:
#                 spans.append(
#                     (
#                         start,
#                         previous,
#                     )
#                 )

#                 start = index
#                 previous = index
#                 continue

#             relation = boundaries.get(
#                 previous,
#                 "new_product",
#             )

#             if (
#                 relation
#                 != "same_product"
#             ):
#                 spans.append(
#                     (
#                         start,
#                         previous,
#                     )
#                 )

#                 start = index

#             previous = index

#         spans.append(
#             (
#                 start,
#                 previous,
#             )
#         )

#         return spans

#     @staticmethod
#     def _names_from_spans(
#         tokens: Sequence[str],
#         spans: Sequence[Span],
#     ) -> List[str]:
#         return [
#             " ".join(
#                 tokens[
#                     start : end + 1
#                 ]
#             ).strip()
#             for start, end in spans
#             if 0 <= start <= end < len(tokens)
#         ]

#     # =========================================================================
#     # NUMBER / UNIT SPANS
#     # =========================================================================

#     @staticmethod
#     def _contiguous_spans_for_role(
#         roles: Dict[int, str],
#         token_count: int,
#         wanted_role: str,
#     ) -> List[Span]:
#         indexes = [
#             index
#             for index in range(
#                 token_count
#             )
#             if roles.get(
#                 index
#             ) == wanted_role
#         ]

#         if not indexes:
#             return []

#         spans: List[
#             Span
#         ] = []

#         start = indexes[0]
#         previous = indexes[0]

#         for index in indexes[1:]:
#             if index != previous + 1:
#                 spans.append(
#                     (
#                         start,
#                         previous,
#                     )
#                 )

#                 start = index

#             previous = index

#         spans.append(
#             (
#                 start,
#                 previous,
#             )
#         )

#         return spans

#     @staticmethod
#     def _span_text(
#         tokens: Sequence[str],
#         span: Optional[Span],
#     ) -> str:
#         if span is None:
#             return ""

#         start, end = span

#         return " ".join(
#             tokens[
#                 start : end + 1
#             ]
#         ).strip()

#     @staticmethod
#     def _find_adjacent_unit_span(
#         quantity_span: Span,
#         unit_spans: Sequence[Span],
#     ) -> Optional[Span]:
#         q_start, q_end = quantity_span

#         # Prefer unit immediately AFTER quantity:
#         #   "ஒரு லிட்டர்"
#         for unit_span in unit_spans:
#             u_start, _ = unit_span

#             if u_start == q_end + 1:
#                 return unit_span

#         # Support unit immediately BEFORE quantity:
#         #   "பாக்கெட் ஒன்னு"
#         for unit_span in unit_spans:
#             _, u_end = unit_span

#             if u_end + 1 == q_start:
#                 return unit_span

#         return None

#     @staticmethod
#     def _associate_product_index(
#         quantity_span: Span,
#         unit_span: Optional[Span],
#         product_spans: Sequence[Span],
#     ) -> Optional[int]:
#         if not product_spans:
#             return None

#         region_start = quantity_span[0]
#         region_end = quantity_span[1]

#         if unit_span is not None:
#             region_start = min(
#                 region_start,
#                 unit_span[0],
#             )

#             region_end = max(
#                 region_end,
#                 unit_span[1],
#             )

#         # Normal grocery list grammar:
#         # PRODUCT -> QUANTITY -> UNIT
#         left_candidates = [
#             (
#                 product_index,
#                 region_start
#                 - product_span[1],
#             )
#             for product_index, product_span
#             in enumerate(product_spans)
#             if product_span[1]
#             < region_start
#         ]

#         if left_candidates:
#             left_candidates.sort(
#                 key=lambda item:
#                     item[1]
#             )

#             return left_candidates[
#                 0
#             ][0]

#         # Also support:
#         # QUANTITY -> UNIT -> PRODUCT
#         right_candidates = [
#             (
#                 product_index,
#                 product_span[0]
#                 - region_end,
#             )
#             for product_index, product_span
#             in enumerate(product_spans)
#             if product_span[0]
#             > region_end
#         ]

#         if right_candidates:
#             right_candidates.sort(
#                 key=lambda item:
#                     item[1]
#             )

#             return right_candidates[
#                 0
#             ][0]

#         return None

#     def _build_measurement_candidates(
#         self,
#         tokens: Sequence[str],
#         roles: Dict[int, str],
#         product_spans: Sequence[Span],
#     ) -> List[Dict[str, Any]]:
#         quantity_spans = (
#             self._contiguous_spans_for_role(
#                 roles,
#                 len(tokens),
#                 "number",
#             )
#         )

#         unit_spans = (
#             self._contiguous_spans_for_role(
#                 roles,
#                 len(tokens),
#                 "unit",
#             )
#         )

#         candidates: List[
#             Dict[str, Any]
#         ] = []

#         for measurement_id, quantity_span in enumerate(
#             quantity_spans
#         ):
#             unit_span = (
#                 self._find_adjacent_unit_span(
#                     quantity_span,
#                     unit_spans,
#                 )
#             )

#             product_index = (
#                 self._associate_product_index(
#                     quantity_span,
#                     unit_span,
#                     product_spans,
#                 )
#             )

#             candidates.append(
#                 {
#                     "measurement_id":
#                         measurement_id,

#                     "product_index":
#                         product_index,

#                     "quantity_span":
#                         quantity_span,

#                     "unit_span":
#                         unit_span,

#                     "quantity_text":
#                         self._span_text(
#                             tokens,
#                             quantity_span,
#                         ),

#                     "explicit_unit_text":
#                         self._span_text(
#                             tokens,
#                             unit_span,
#                         ),
#                 }
#             )

#         return candidates

#     # =========================================================================
#     # SEMANTIC MEASUREMENT PARSING
#     # =========================================================================

#     def _parse_one_measurement(
#         self,
#         quantity_text: str,
#         explicit_unit_text: str,
#     ) -> Tuple[
#         Quantity,
#         str,
#     ]:
#         result = self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content":
#                         SINGLE_MEASUREMENT_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         f"quantity_text: {quantity_text}\n"
#                         "explicit_unit_text: "
#                         f"{explicit_unit_text}\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             schema=self._single_measurement_schema(),
#             max_tokens=120,
#         )

#         quantity = (
#             self._parse_quantity(
#                 result.get(
#                     "quantity"
#                 )
#             )
#         )

#         unit = (
#             self._normalize_unit(
#                 result.get(
#                     "unit",
#                     "unknown",
#                 )
#             )
#         )

#         return (
#             quantity,
#             unit,
#         )

#     def _parse_measurement_candidates(
#         self,
#         candidates: Sequence[
#             Dict[str, Any]
#         ],
#     ) -> Dict[
#         int,
#         Dict[str, Any],
#     ]:
#         if not candidates:
#             return {}

#         rows = "\n".join(
#             (
#                 f"{candidate['measurement_id']}: "
#                 f"quantity_text={candidate['quantity_text']!r}; "
#                 "explicit_unit_text="
#                 f"{candidate['explicit_unit_text']!r}"
#             )
#             for candidate in candidates
#         )

#         batch_result: Dict[
#             int,
#             Dict[str, Any],
#         ] = {}

#         try:
#             result = self._call_json(
#                 messages=[
#                     {
#                         "role": "system",
#                         "content":
#                             MEASUREMENT_PARSE_PROMPT,
#                     },
#                     {
#                         "role": "user",
#                         "content": (
#                             "MEASUREMENTS:\n"
#                             f"{rows}\n"
#                             "/no_think"
#                         ),
#                     },
#                 ],
#                 schema=self._measurement_schema(),
#                 max_tokens=max(
#                     350,
#                     len(candidates) * 90,
#                 ),
#             )

#             raw = result.get(
#                 "measurements",
#                 [],
#             )

#             if isinstance(
#                 raw,
#                 list,
#             ):
#                 valid_ids = {
#                     int(
#                         candidate[
#                             "measurement_id"
#                         ]
#                     )
#                     for candidate
#                     in candidates
#                 }

#                 for row in raw:
#                     if not isinstance(
#                         row,
#                         dict,
#                     ):
#                         continue

#                     measurement_id = (
#                         row.get(
#                             "measurement_id"
#                         )
#                     )

#                     if (
#                         isinstance(
#                             measurement_id,
#                             bool,
#                         )
#                         or
#                         not isinstance(
#                             measurement_id,
#                             int,
#                         )
#                         or
#                         measurement_id
#                         not in valid_ids
#                     ):
#                         continue

#                     quantity = (
#                         self._parse_quantity(
#                             row.get(
#                                 "quantity"
#                             )
#                         )
#                     )

#                     unit = (
#                         self._normalize_unit(
#                             row.get(
#                                 "unit",
#                                 "unknown",
#                             )
#                         )
#                     )

#                     if quantity is None:
#                         continue

#                     batch_result[
#                         measurement_id
#                     ] = {
#                         "quantity":
#                             quantity,

#                         "unit":
#                             unit,
#                     }

#         except Exception as error:
#             print(
#                 "Batch measurement parse failed:",
#                 error,
#                 flush=True,
#             )

#         # Focused retry for missing/invalid rows.
#         for candidate in candidates:
#             measurement_id = int(
#                 candidate[
#                     "measurement_id"
#                 ]
#             )

#             if (
#                 measurement_id
#                 in batch_result
#             ):
#                 continue

#             try:
#                 quantity, unit = (
#                     self._parse_one_measurement(
#                         quantity_text=str(
#                             candidate[
#                                 "quantity_text"
#                             ]
#                         ),
#                         explicit_unit_text=str(
#                             candidate[
#                                 "explicit_unit_text"
#                             ]
#                         ),
#                     )
#                 )

#                 if quantity is not None:
#                     batch_result[
#                         measurement_id
#                     ] = {
#                         "quantity":
#                             quantity,

#                         "unit":
#                             unit,
#                     }

#             except Exception as error:
#                 print(
#                     "Focused measurement parse "
#                     f"failed for {candidate['quantity_text']}:",
#                     error,
#                     flush=True,
#                 )

#         return batch_result

#     # =========================================================================
#     # UNIT INFERENCE
#     # =========================================================================

#     def _infer_one_unit(
#         self,
#         product_name: str,
#         quantity: Quantity,
#     ) -> str:
#         result = self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content":
#                         SINGLE_UNIT_INFERENCE_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         f"product_name: {product_name}\n"
#                         f"quantity: {quantity}\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             schema=self._single_unit_schema(),
#             max_tokens=80,
#         )

#         return self._normalize_unit(
#             result.get(
#                 "unit",
#                 "unknown",
#             )
#         )

#     def _infer_missing_units(
#         self,
#         products: Sequence[str],
#         rows: Sequence[
#             Dict[str, Any]
#         ],
#     ) -> Dict[int, str]:
#         """
#         rows contain:
#             product_index
#             quantity
#         only for measurements with NO explicit normalized unit.
#         """

#         if not rows:
#             return {}

#         prompt_rows = "\n".join(
#             (
#                 f"product_index={row['product_index']} | "
#                 f"product_name={products[row['product_index']]} | "
#                 f"quantity={row['quantity']}"
#             )
#             for row in rows
#             if (
#                 isinstance(
#                     row.get(
#                         "product_index"
#                     ),
#                     int,
#                 )
#                 and
#                 0
#                 <= int(
#                     row[
#                         "product_index"
#                     ]
#                 )
#                 < len(products)
#             )
#         )

#         inferred: Dict[
#             int,
#             str,
#         ] = {}

#         try:
#             result = self._call_json(
#                 messages=[
#                     {
#                         "role": "system",
#                         "content":
#                             UNIT_INFERENCE_PROMPT,
#                     },
#                     {
#                         "role": "user",
#                         "content": (
#                             "PRODUCTS NEEDING UNIT INFERENCE:\n"
#                             f"{prompt_rows}\n"
#                             "/no_think"
#                         ),
#                     },
#                 ],
#                 schema=self._unit_inference_schema(),
#                 max_tokens=max(
#                     250,
#                     len(rows) * 55,
#                 ),
#             )

#             raw = result.get(
#                 "units",
#                 [],
#             )

#             if isinstance(
#                 raw,
#                 list,
#             ):
#                 valid_indexes = {
#                     int(
#                         row[
#                             "product_index"
#                         ]
#                     )
#                     for row in rows
#                     if isinstance(
#                         row.get(
#                             "product_index"
#                         ),
#                         int,
#                     )
#                 }

#                 for item in raw:
#                     if not isinstance(
#                         item,
#                         dict,
#                     ):
#                         continue

#                     product_index = (
#                         item.get(
#                             "product_index"
#                         )
#                     )

#                     if (
#                         isinstance(
#                             product_index,
#                             bool,
#                         )
#                         or
#                         not isinstance(
#                             product_index,
#                             int,
#                         )
#                         or
#                         product_index
#                         not in valid_indexes
#                     ):
#                         continue

#                     inferred[
#                         product_index
#                     ] = (
#                         self._normalize_unit(
#                             item.get(
#                                 "unit",
#                                 "unknown",
#                             )
#                         )
#                     )

#         except Exception as error:
#             print(
#                 "Batch unit inference failed:",
#                 error,
#                 flush=True,
#             )

#         for row in rows:
#             product_index = row.get(
#                 "product_index"
#             )

#             if (
#                 isinstance(
#                     product_index,
#                     bool,
#                 )
#                 or
#                 not isinstance(
#                     product_index,
#                     int,
#                 )
#                 or
#                 not (
#                     0
#                     <= product_index
#                     < len(products)
#                 )
#                 or
#                 product_index
#                 in inferred
#             ):
#                 continue

#             try:
#                 inferred[
#                     product_index
#                 ] = (
#                     self._infer_one_unit(
#                         product_name=
#                             products[
#                                 product_index
#                             ],
#                         quantity=
#                             row.get(
#                                 "quantity"
#                             ),
#                     )
#                 )

#             except Exception as error:
#                 print(
#                     "Focused unit inference "
#                     f"failed for {products[product_index]}:",
#                     error,
#                     flush=True,
#                 )

#                 inferred[
#                     product_index
#                 ] = "unknown"

#         return inferred

#     # =========================================================================
#     # FINAL ITEMS
#     # =========================================================================

#     @staticmethod
#     def _build_item(
#         spoken_name: str,
#         quantity: Quantity,
#         unit: str,
#     ) -> Dict[str, Any]:
#         spoken_name = str(
#             spoken_name or ""
#         ).strip()

#         unit = str(
#             unit or "unknown"
#         ).strip().lower()

#         if not unit:
#             unit = "unknown"

#         if (
#             quantity is not None
#             and
#             unit != "unknown"
#         ):
#             return {
#                 "spoken_name":
#                     spoken_name,

#                 "search_name":
#                     spoken_name,

#                 "quantity":
#                     quantity,

#                 "unit":
#                     unit,

#                 "search_mode":
#                     "specific_variant",
#             }

#         if quantity is not None:
#             return {
#                 "spoken_name":
#                     spoken_name,

#                 "search_name":
#                     spoken_name,

#                 "quantity":
#                     quantity,

#                 "unit":
#                     "unknown",

#                 "search_mode":
#                     "related_products",
#             }

#         return {
#             "spoken_name":
#                 spoken_name,

#             "search_name":
#                 spoken_name,

#             "quantity":
#                 None,

#             "unit":
#                 "unknown",

#             "search_mode":
#                 "related_products",
#         }

#     def _build_final_items(
#         self,
#         products: Sequence[str],
#         candidates: Sequence[
#             Dict[str, Any]
#         ],
#         parsed_measurements: Dict[
#             int,
#             Dict[str, Any],
#         ],
#     ) -> List[Dict[str, Any]]:
#         by_product: Dict[
#             int,
#             Dict[str, Any],
#         ] = {}

#         # Attach parsed quantities to products.
#         for candidate in candidates:
#             measurement_id = int(
#                 candidate[
#                     "measurement_id"
#                 ]
#             )

#             product_index = candidate.get(
#                 "product_index"
#             )

#             if (
#                 isinstance(
#                     product_index,
#                     bool,
#                 )
#                 or
#                 not isinstance(
#                     product_index,
#                     int,
#                 )
#                 or
#                 not (
#                     0
#                     <= product_index
#                     < len(products)
#                 )
#             ):
#                 continue

#             parsed = (
#                 parsed_measurements.get(
#                     measurement_id
#                 )
#             )

#             if parsed is None:
#                 continue

#             quantity = parsed.get(
#                 "quantity"
#             )

#             unit = str(
#                 parsed.get(
#                     "unit",
#                     "unknown",
#                 )
#             )

#             # One normal grocery list quantity belongs to one product.
#             # Keep the first valid measurement rather than letting a later
#             # model row overwrite it.
#             if product_index not in by_product:
#                 by_product[
#                     product_index
#                 ] = {
#                     "quantity":
#                         quantity,

#                     "unit":
#                         unit,

#                     "explicit_unit":
#                         bool(
#                             candidate.get(
#                                 "explicit_unit_text"
#                             )
#                         ),
#                 }

#         # Infer natural units ONLY where:
#         # - a quantity exists
#         # - customer did not explicitly say a unit
#         # - parsed unit is still unknown
#         need_unit_inference: List[
#             Dict[str, Any]
#         ] = []

#         for product_index, measurement in by_product.items():
#             if (
#                 measurement.get(
#                     "quantity"
#                 )
#                 is None
#             ):
#                 continue

#             if measurement.get(
#                 "explicit_unit"
#             ):
#                 continue

#             if (
#                 str(
#                     measurement.get(
#                         "unit",
#                         "unknown",
#                     )
#                 )
#                 != "unknown"
#             ):
#                 continue

#             need_unit_inference.append(
#                 {
#                     "product_index":
#                         product_index,

#                     "quantity":
#                         measurement.get(
#                             "quantity"
#                         ),
#                 }
#             )

#         inferred_units = (
#             self._infer_missing_units(
#                 products,
#                 need_unit_inference,
#             )
#         )

#         for product_index, inferred_unit in inferred_units.items():
#             if product_index in by_product:
#                 by_product[
#                     product_index
#                 ][
#                     "unit"
#                 ] = inferred_unit

#         final_items: List[
#             Dict[str, Any]
#         ] = []

#         for product_index, product_name in enumerate(
#             products
#         ):
#             measurement = (
#                 by_product.get(
#                     product_index
#                 )
#             )

#             if measurement is None:
#                 final_items.append(
#                     self._build_item(
#                         spoken_name=
#                             product_name,
#                         quantity=None,
#                         unit="unknown",
#                     )
#                 )

#                 continue

#             final_items.append(
#                 self._build_item(
#                     spoken_name=
#                         product_name,

#                     quantity=
#                         measurement.get(
#                             "quantity"
#                         ),

#                     unit=str(
#                         measurement.get(
#                             "unit",
#                             "unknown",
#                         )
#                     ),
#                 )
#             )

#         return final_items

#     # =========================================================================
#     # MAIN PARSER
#     # =========================================================================

#     def parse(
#         self,
#         transcript: str,
#     ) -> Dict[str, Any]:
#         transcript = (
#             self._normalize_text(
#                 transcript
#             )
#         )

#         if not transcript:
#             return {
#                 "items": [],
#             }

#         tokens = (
#             self._tokenize(
#                 transcript
#             )
#         )

#         if not tokens:
#             return {
#                 "items": [],
#             }

#         print(
#             "PARSER TOKENS:",
#             tokens,
#             flush=True,
#         )

#         # ---------------------------------------------------------------------
#         # 1. Classify only token semantics.
#         # ---------------------------------------------------------------------

#         roles = (
#             self._classify_token_roles(
#                 transcript,
#                 tokens,
#             )
#         )

#         print(
#             "FINAL TOKEN ROLES:",
#             [
#                 (
#                     index,
#                     tokens[index],
#                     roles.get(
#                         index,
#                         "word",
#                     ),
#                 )
#                 for index
#                 in range(
#                     len(tokens)
#                 )
#             ],
#             flush=True,
#         )

#         # ---------------------------------------------------------------------
#         # 2. Resolve only product-word boundaries.
#         # ---------------------------------------------------------------------

#         boundaries = (
#             self._resolve_product_boundaries(
#                 transcript,
#                 tokens,
#                 roles,
#             )
#         )

#         print(
#             "FINAL PRODUCT BOUNDARIES:",
#             boundaries,
#             flush=True,
#         )

#         product_spans = (
#             self._build_product_spans(
#                 tokens,
#                 roles,
#                 boundaries,
#             )
#         )

#         products = (
#             self._names_from_spans(
#                 tokens,
#                 product_spans,
#             )
#         )

#         print(
#             "FINAL PRODUCT SPANS:",
#             product_spans,
#             flush=True,
#         )

#         print(
#             "FINAL PRODUCTS:",
#             products,
#             flush=True,
#         )

#         if not products:
#             return {
#                 "items": [],
#             }

#         # ---------------------------------------------------------------------
#         # 3. Build quantity/unit regions and attach each to nearest product.
#         # ---------------------------------------------------------------------

#         candidates = (
#             self._build_measurement_candidates(
#                 tokens,
#                 roles,
#                 product_spans,
#             )
#         )

#         print(
#             "MEASUREMENT CANDIDATES:",
#             candidates,
#             flush=True,
#         )

#         # ---------------------------------------------------------------------
#         # 4. Convert Tamil/Tanglish/English/ASR number phrases semantically.
#         # ---------------------------------------------------------------------

#         parsed_measurements = (
#             self._parse_measurement_candidates(
#                 candidates
#             )
#         )

#         print(
#             "PARSED MEASUREMENTS:",
#             parsed_measurements,
#             flush=True,
#         )

#         # ---------------------------------------------------------------------
#         # 5. Explicit units already normalized above.
#         #    Missing units are inferred from product semantics here.
#         # ---------------------------------------------------------------------

#         final_items = (
#             self._build_final_items(
#                 products,
#                 candidates,
#                 parsed_measurements,
#             )
#         )

#         print(
#             "FINAL PARSED ITEMS:",
#             final_items,
#             flush=True,
#         )

#         return {
#             "items":
#                 final_items,
#         }


# # Single global instance used by FastAPI:
# # from grocery_parser import grocery_parser
# grocery_parser = GroceryParser()































# import json
# import re

# from llama_cpp import Llama


# MODEL_PATH = (
#     "/home/hari/voicesearch_ai/models/"
#     "Qwen3-1.7B-Q4_K_M.gguf"
# )


# SYSTEM_PROMPT = """
# You are an AI parser for grocery voice search.

# Customers may speak naturally in:
# - Tamil
# - colloquial Tamil
# - Tanglish
# - English
# - mixed Tamil and English

# Your job is to understand the meaning of the customer's request.

# Do NOT use database knowledge.
# Do NOT invent products.
# Do NOT invent quantities.
# Do NOT invent units.
# Do NOT invent product IDs or variant IDs.


# ==================================================
# PRODUCT
# ==================================================

# Preserve the product wording from the customer's speech.

# Example:

# Customer:
# பச்சரிசி

# Return:

# spoken_name = "பச்சரிசி"
# search_name = "பச்சரிசி"

# Do NOT automatically change it to another database spelling.


# ==================================================
# QUANTITY
# ==================================================

# Understand quantities semantically.

# Examples:

# அம்பது
# ஐம்பது
# fifty
# 50

# all represent the number 50.

# Understand normal Tamil, colloquial Tamil,
# Tanglish and English numbers.

# Understand fractions naturally:

# அரை
# half

# கால்
# quarter

# ஒன்னரை
# one and a half


# ==================================================
# WEIGHT
# ==================================================

# When the customer specifies a weight,
# normalize the result to grams.

# Examples:

# 50 grams
# -> quantity = "50"
# -> unit = "g"

# 1 kilogram
# -> quantity = "1000"
# -> unit = "g"

# அரை கிலோ
# -> quantity = "500"
# -> unit = "g"

# கால் கிலோ
# -> quantity = "250"
# -> unit = "g"


# ==================================================
# LIQUID VOLUME
# ==================================================

# When the customer specifies liquid volume,
# normalize the result to millilitres.

# Examples:

# 500 millilitres
# -> quantity = "500"
# -> unit = "ml"

# 1 litre
# -> quantity = "1000"
# -> unit = "ml"

# அரை லிட்டர்
# -> quantity = "500"
# -> unit = "ml"

# quarter litre
# -> quantity = "250"
# -> unit = "ml"


# ==================================================
# COUNTABLE / PACKAGED PRODUCTS
# ==================================================

# If a customer asks for a countable quantity,
# preserve the semantic package/count type.

# Examples:

# one packet
# ஒரு பாக்கெட்

# -> quantity = "1"
# -> unit = "packet"

# two bottles
# -> quantity = "2"
# -> unit = "bottle"

# one box
# -> quantity = "1"
# -> unit = "box"

# three pieces
# -> quantity = "3"
# -> unit = "pcs"

# Do not convert package/container units into weight or volume
# unless the customer explicitly states a weight or volume.


# ==================================================
# NO QUANTITY
# ==================================================

# A customer may say only the product name.

# Example:

# Customer:
# சீரகம்

# Return:

# quantity = ""
# unit = "unknown"

# This means the application should show all related products.

# Never invent a default quantity.


# ==================================================
# QUANTITY BUT NO UNIT
# ==================================================

# Example:

# Customer:
# சீரகம் அம்பது

# Understand:

# quantity = "50"
# unit = "unknown"

# Do NOT guess:
# 50 grams
# 50 pieces
# 50 packets

# The backend will handle this as a general product search.


# ==================================================
# UNIT NORMALIZATION
# ==================================================

# Understand unit words by their meaning, regardless of language,
# spelling style or colloquial pronunciation.

# For weight:
# return unit = "g"

# For liquid volume:
# return unit = "ml"

# For individual count:
# return unit = "pcs"

# For a package/container:
# return a simple canonical English unit describing that container,
# for example:
# packet
# bottle
# box
# bag
# can
# jar
# carton
# bundle
# bunch
# roll

# If no reliable unit is present:
# return unit = "unknown"

# Do not return raw measurement words such as:
# liter
# litre
# kg
# kilogram

# Convert measurement units to the canonical units above.


# ==================================================
# UNIT SPOKEN
# ==================================================

# Also return:

# unit_spoken

# This must contain the unit phrase actually heard in the transcript.

# Example:

# Customer:
# நல்லெண்ணெய் ஒரு லிட்டர்

# Return:

# quantity = "1000"
# unit = "ml"
# unit_spoken = "லிட்டர்"


# Customer:
# milk one litre

# Return:

# quantity = "1000"
# unit = "ml"
# unit_spoken = "litre"


# If no unit was spoken:

# unit = "unknown"
# unit_spoken = ""


# ==================================================
# SEARCH MODE
# ==================================================

# Determine search behavior.

# If BOTH a meaningful quantity and a definite unit exist:

# search_mode = "specific_variant"

# Example:

# சீரகம் 50 கிராம்

# -> specific_variant


# If quantity is missing:

# search_mode = "related_products"


# If quantity exists but unit is unknown:

# search_mode = "related_products"


# Examples:

# சீரகம்
# -> related_products

# சீரகம் அம்பது
# -> related_products

# சீரகம் அம்பது கிராம்
# -> specific_variant


# ==================================================
# MULTIPLE PRODUCTS
# ==================================================

# The customer may mention many products in one sentence.

# Extract every product separately.

# Each item may independently be either:
# specific_variant
# or
# related_products

# Never attach one item's quantity to another product.


# ==================================================
# QUANTITY FORMAT
# ==================================================

# quantity must always be a STRING.

# Correct:

# "50"
# "500"
# "1000"
# "1"

# If quantity was not spoken:

# ""

# Do not return quantity as a JSON number.


# ==================================================
# OUTPUT
# ==================================================

# Return ONLY valid JSON.

# No markdown.
# No explanation.
# No comments.
# No additional text.

# /no_think
# """


# class GroceryParser:

#     def __init__(self):

#         print("Loading Qwen grocery parser...")

#         self.llm = Llama(
#             model_path=MODEL_PATH,
#             n_ctx=4096,
#             n_threads=4,
#             n_batch=128,
#             verbose=False,
#             seed=42,
#         )

#         print("Qwen grocery parser ready.")

#     def _generate(self, transcript: str) -> dict:

#         response = self.llm.create_chat_completion(
#             messages=[
#                 {
#                     "role": "system",
#                     "content": SYSTEM_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "Customer speech:\n"
#                         + transcript
#                         + "\n/no_think"
#                     ),
#                 },
#             ],

#             response_format={
#                 "type": "json_object",

#                 "schema": {
#                     "type": "object",

#                     "properties": {

#                         "items": {
#                             "type": "array",

#                             "items": {
#                                 "type": "object",

#                                 "properties": {

#                                     "spoken_name": {
#                                         "type": "string"
#                                     },

#                                     "search_name": {
#                                         "type": "string"
#                                     },

#                                     "quantity": {
#                                         "type": "string"
#                                     },

#                                     "unit": {
#                                         "type": "string"
#                                     },

#                                     "unit_spoken": {
#                                         "type": "string"
#                                     },

#                                     "search_mode": {
#                                         "type": "string",
#                                         "enum": [
#                                             "specific_variant",
#                                             "related_products"
#                                         ]
#                                     }
#                                 },

#                                 "required": [
#                                     "spoken_name",
#                                     "search_name",
#                                     "quantity",
#                                     "unit",
#                                     "unit_spoken",
#                                     "search_mode"
#                                 ]
#                             }
#                         }
#                     },

#                     "required": ["items"]
#                 }
#             },

#             temperature=0.0,
#             max_tokens=700,
#         )

#         text = (
#             response["choices"][0]
#             ["message"]["content"]
#         )

#         try:
#             return json.loads(text)

#         except json.JSONDecodeError as error:

#             print("Invalid Qwen JSON:")
#             print(text)

#             raise ValueError(
#                 "Qwen returned invalid JSON"
#             ) from error

#     def _clean_result(
#         self,
#         result: dict,
#     ) -> dict:

#         items = result.get("items")

#         if not isinstance(items, list):
#             raise ValueError(
#                 "Invalid items result"
#             )

#         cleaned = []

#         for item in items:

#             spoken_name = str(
#                 item.get("spoken_name", "")
#             ).strip()

#             search_name = str(
#                 item.get("search_name", "")
#             ).strip()

#             quantity_text = str(
#                 item.get("quantity", "")
#             ).strip()

#             unit = str(
#                 item.get("unit", "unknown")
#             ).strip().lower()

#             search_mode = str(
#                 item.get(
#                     "search_mode",
#                     "related_products"
#                 )
#             ).strip()

#             if not spoken_name:
#                 continue

#             if not search_name:
#                 search_name = spoken_name

#             # No quantity was spoken
#             if not quantity_text:

#                 quantity = None
#                 unit = "unknown"
#                 search_mode = (
#                     "related_products"
#                 )

#             else:

#                 if not re.fullmatch(
#                     r"\d+",
#                     quantity_text
#                 ):
#                     raise ValueError(
#                         "Invalid quantity returned "
#                         "by AI"
#                     )

#                 quantity = int(
#                     quantity_text
#                 )

#                 if quantity <= 0:
#                     raise ValueError(
#                         "Invalid quantity"
#                     )

#                 # If AI cannot confidently
#                 # determine a unit, never guess
#                 if not unit:
#                     unit = "unknown"

#                 if unit == "unknown":
#                     search_mode = (
#                         "related_products"
#                     )

#                 else:
#                     search_mode = (
#                         "specific_variant"
#                     )

#             cleaned.append(
#                 {
#                     "spoken_name":
#                         spoken_name,

#                     "search_name":
#                         search_name,

#                     "quantity":
#                         quantity,

#                     "unit":
#                         unit,

#                     "search_mode":
#                         search_mode,
#                 }
#             )

#         return {
#             "items": cleaned
#         }

#     def parse(
#         self,
#         transcript: str,
#     ) -> dict:

#         result = self._generate(
#             transcript
#         )

#         return self._clean_result(
#             result
#         )


# grocery_parser = GroceryParser()










# import json
# from typing import Any, Dict, List, Optional

# from llama_cpp import Llama


# MODEL_PATH = (
#     "/home/hari/voicesearch_ai/models/"
#     "Qwen3-1.7B-Q4_K_M.gguf"
# )


# # ============================================================
# # MAIN SYSTEM PROMPT
# # ============================================================

# SYSTEM_PROMPT = """
# You are a grocery voice-search parser.

# The customer may speak:

# - Tamil
# - colloquial Tamil
# - Tanglish
# - English
# - mixed Tamil and English

# Your job is to extract EVERY grocery product from the customer's
# speech together with the quantity and unit that actually belong
# to that product.

# You are NOT searching a database.

# Never invent:
# - products
# - quantities
# - units
# - product IDs
# - variant IDs


# ============================================================
# 1. PRODUCT NAME
# ============================================================

# Preserve product names as the customer said them.

# Do not translate Tamil product names.

# Do not transliterate Tamil product names into English.

# VERY IMPORTANT:

# A natural multi-word grocery name must remain ONE product.

# Examples:

# சிக்கன் மசாலா
# -> ONE product: "சிக்கன் மசாலா"

# சாம்பார் பொடி
# -> ONE product: "சாம்பார் பொடி"

# chicken masala
# -> ONE product: "chicken masala"

# coconut oil
# -> ONE product: "coconut oil"

# Do NOT split:

# "சிக்கன் மசாலா"

# into:

# "சிக்கன்"
# "மசாலா"


# ============================================================
# 2. QUANTITY
# ============================================================

# Understand quantities semantically.

# Tamil, colloquial Tamil, Tanglish and English number expressions
# must be understood naturally.

# Examples:

# அம்பது -> 50
# ஐம்பது -> 50
# fifty -> 50

# நூறு -> 100
# hundred -> 100

# ஒரு -> 1
# ஒன்னு -> 1
# one -> 1

# ரெண்டு -> 2
# two -> 2

# மூணு -> 3

# Understand fractions naturally:

# அரை -> half
# கால் -> quarter
# ஒன்னரை -> one and a half


# ============================================================
# 3. WEIGHT
# ============================================================

# ONLY when a weight unit is actually spoken,
# normalize the value to grams.

# Examples:

# சீரகம் ஐம்பது கிராம்
# -> quantity = "50"
# -> unit = "g"

# பச்சரிசி ஒரு கிலோ
# -> quantity = "1000"
# -> unit = "g"

# தக்காளி அரை கிலோ
# -> quantity = "500"
# -> unit = "g"

# கால் கிலோ
# -> quantity = "250"
# -> unit = "g"

# 2 kilograms
# -> quantity = "2000"
# -> unit = "g"


# ============================================================
# 4. LIQUID
# ============================================================

# ONLY when a liquid-volume unit is actually spoken,
# normalize the value to millilitres.

# Examples:

# ஒரு லிட்டர்
# -> quantity = "1000"
# -> unit = "ml"

# அரை லிட்டர்
# -> quantity = "500"
# -> unit = "ml"

# 500 ml
# -> quantity = "500"
# -> unit = "ml"


# ============================================================
# 5. PACKAGE / COUNT
# ============================================================

# Understand an explicitly spoken package/count unit naturally.

# Examples:

# ஒரு பாக்கெட்
# -> quantity = "1"
# -> unit = "packet"

# பாக்கெட் ஒன்னு
# -> quantity = "1"
# -> unit = "packet"

# two packets
# -> quantity = "2"
# -> unit = "packet"

# 2 pieces
# -> quantity = "2"
# -> unit = "pcs"

# one bottle
# -> quantity = "1"
# -> unit = "bottle"


# ============================================================
# 6. QUANTITY BUT NO UNIT
# ============================================================

# This rule is extremely important.

# If the customer says a product and quantity,
# but NO unit is actually spoken:

# KEEP the quantity.

# Set:

# unit = "unknown"

# Example:

# சீரகம் அம்பது

# Correct:

# {
#   "spoken_name": "சீரகம்",
#   "quantity": "50",
#   "unit": "unknown"
# }

# Never change it to:

# 50 g
# 50 pcs
# 50 packet
# 50 ml

# because the customer did not say a unit.


# ============================================================
# 7. PRODUCT ONLY
# ============================================================

# If the customer gives only the product name:

# quantity = ""
# unit = "unknown"

# Example:

# சீரகம்

# Correct:

# {
#   "spoken_name": "சீரகம்",
#   "quantity": "",
#   "unit": "unknown"
# }


# ============================================================
# 8. NEVER INFER UNIT FROM PRODUCT TYPE
# ============================================================

# Do NOT assume:

# powder -> grams
# vegetable -> kilograms
# oil -> litres
# item -> pieces

# A unit is known ONLY when the speech actually communicates it.

# If the speech says:

# மிளகாப்பொடி நூறு

# then:

# quantity = "100"
# unit = "unknown"

# Do NOT return "pcs".
# Do NOT return "g".

# If the speech says:

# மிளகாப்பொடி நூறு கிராம்

# then:

# quantity = "100"
# unit = "g"


# ============================================================
# 9. MULTIPLE PRODUCTS
# ============================================================

# Keep the correct quantity/unit attached to the correct product.

# Example:

# சீரகம் ஐம்பது கிராம்
# பச்சரிசி ஒரு கிலோ
# தக்காளி அரை கிலோ

# Return three items.


# IMPORTANT EXAMPLE:

# Customer speech:

# சிக்கன் மசாலா அம்பது
# மிளகாப்பொடி நூறு
# சூட பாக்கெட் ஒன்னு

# Correct interpretation:

# 1.
# spoken_name = "சிக்கன் மசாலா"
# quantity = "50"
# unit = "unknown"

# 2.
# spoken_name = "மிளகாப்பொடி"
# quantity = "100"
# unit = "unknown"

# 3.
# spoken_name = "சூட"
# quantity = "1"
# unit = "packet"

# There are THREE products.

# Do not split "சிக்கன் மசாலா".

# Do not invent "piece" for the first two products.


# ============================================================
# 10. OUTPUT
# ============================================================

# quantity MUST be a string.

# Examples:

# "50"
# "100"
# "500"
# "1000"
# "1"
# ""

# Return exactly:

# {
#   "items": [
#     {
#       "spoken_name": "...",
#       "quantity": "...",
#       "unit": "..."
#     }
#   ]
# }

# Return ONLY valid JSON.

# No markdown.
# No explanation.
# No comments.
# No reasoning.

# /no_think
# """


# # ============================================================
# # SECOND-PASS AUDITOR
# # ============================================================

# AUDIT_PROMPT = """
# You are the final accuracy checker for a grocery voice search.

# You receive:

# 1. the ORIGINAL speech transcript
# 2. a draft parsed result

# Return a corrected final result.

# Check ALL of these:

# - every grocery product in the original speech is present
# - no product was invented
# - natural multi-word product names remain together
# - quantities belong to the correct product
# - spoken Tamil/colloquial numbers are converted correctly
# - a unit is used ONLY when the speech communicates that unit
# - NEVER invent grams, pieces, packets, litres, etc.
# - if quantity exists but unit is missing:
#     KEEP quantity
#     unit = "unknown"
# - if product has no quantity:
#     quantity = ""
#     unit = "unknown"
# - explicitly spoken weight -> normalize to grams
# - explicitly spoken liquid volume -> normalize to millilitres
# - explicitly spoken package/count -> preserve an appropriate
#   canonical package/count unit

# Important:

# சிக்கன் மசாலா is one product.

# "அம்பது" means 50.
# "நூறு" means 100.
# "ஒன்னு" means 1.

# Example:

# Original:
# சிக்கன் மசாலா அம்பது மிளகாப்பொடி நூறு சூட பாக்கெட் ஒன்னு

# Correct:

# {
#   "items": [
#     {
#       "spoken_name": "சிக்கன் மசாலா",
#       "quantity": "50",
#       "unit": "unknown"
#     },
#     {
#       "spoken_name": "மிளகாப்பொடி",
#       "quantity": "100",
#       "unit": "unknown"
#     },
#     {
#       "spoken_name": "சூட",
#       "quantity": "1",
#       "unit": "packet"
#     }
#   ]
# }

# Return JSON only.
# No explanation.
# No markdown.

# /no_think
# """


# class GroceryParser:

#     def __init__(self):

#         print(
#             "Loading Qwen grocery parser...",
#             flush=True,
#         )

#         self.llm = Llama(
#             model_path=MODEL_PATH,
#             n_ctx=4096,
#             n_threads=4,
#             n_batch=128,
#             verbose=False,
#             seed=42,
#         )

#         print(
#             "Qwen grocery parser ready.",
#             flush=True,
#         )


#     # ========================================================
#     # JSON SCHEMA
#     # ========================================================

#     @staticmethod
#     def _items_schema():

#         return {
#             "type": "object",
#             "properties": {
#                 "items": {
#                     "type": "array",
#                     "items": {
#                         "type": "object",
#                         "properties": {
#                             "spoken_name": {
#                                 "type": "string"
#                             },
#                             "quantity": {
#                                 "type": "string"
#                             },
#                             "unit": {
#                                 "type": "string"
#                             },
#                         },
#                         "required": [
#                             "spoken_name",
#                             "quantity",
#                             "unit",
#                         ],
#                     },
#                 }
#             },
#             "required": [
#                 "items"
#             ],
#         }


#     # ========================================================
#     # QWEN JSON CALL
#     # ========================================================

#     def _call_json(
#         self,
#         messages,
#         max_tokens=700,
#     ):

#         response = self.llm.create_chat_completion(
#             messages=messages,
#             response_format={
#                 "type": "json_object",
#                 "schema": self._items_schema(),
#             },
#             temperature=0.0,
#             max_tokens=max_tokens,
#         )

#         content = (
#             response
#             .get(
#                 "choices",
#                 [{}],
#             )[0]
#             .get(
#                 "message",
#                 {},
#             )
#             .get(
#                 "content",
#                 "",
#             )
#         )

#         content = str(
#             content or ""
#         ).strip()

#         if not content:
#             raise RuntimeError(
#                 "Qwen returned an empty response"
#             )

#         return json.loads(
#             content
#         )


#     # ========================================================
#     # FIRST PARSE
#     # ========================================================

#     def _generate(
#         self,
#         transcript: str,
#     ):

#         return self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content": SYSTEM_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "Customer speech:\n"
#                         f"{transcript}\n"
#                         "/no_think"
#                     ),
#                 },
#             ],
#             max_tokens=700,
#         )


#     # ========================================================
#     # SECOND PASS
#     #
#     # Qwen checks its own first result against the ORIGINAL
#     # transcript.
#     #
#     # No product aliases / keyword mapping are used.
#     # ========================================================

#     def _audit(
#         self,
#         transcript: str,
#         draft: Dict[str, Any],
#     ):

#         draft_json = json.dumps(
#             draft,
#             ensure_ascii=False,
#         )

#         return self._call_json(
#             messages=[
#                 {
#                     "role": "system",
#                     "content": AUDIT_PROMPT,
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         "ORIGINAL SPEECH:\n"
#                         f"{transcript}\n\n"
#                         "DRAFT RESULT:\n"
#                         f"{draft_json}\n\n"
#                         "Return the corrected final result."
#                     ),
#                 },
#             ],
#             max_tokens=700,
#         )


#     # ========================================================
#     # QUANTITY
#     # ========================================================

#     @staticmethod
#     def _parse_quantity(
#         value: Any,
#     ) -> Optional[int]:

#         text = str(
#             value or ""
#         ).strip()

#         if not text:
#             return None

#         # Qwen must already have converted spoken numbers
#         # to numeric strings.
#         if not text.isdigit():
#             return None

#         quantity = int(
#             text
#         )

#         if quantity <= 0:
#             return None

#         return quantity


#     # ========================================================
#     # BUILD FINAL ITEM
#     # ========================================================

#     def _build_item(
#         self,
#         spoken_name: str,
#         quantity: Optional[int],
#         unit: str,
#     ) -> Dict[str, Any]:

#         spoken_name = str(
#             spoken_name or ""
#         ).strip()

#         unit = str(
#             unit or "unknown"
#         ).strip().lower()

#         if not unit:
#             unit = "unknown"


#         # ----------------------------------------------------
#         # Quantity + explicit unit
#         # ----------------------------------------------------

#         if (
#             quantity is not None
#             and unit != "unknown"
#         ):

#             return {
#                 "spoken_name":
#                     spoken_name,

#                 "search_name":
#                     spoken_name,

#                 "quantity":
#                     quantity,

#                 "unit":
#                     unit,

#                 "search_mode":
#                     "specific_variant",
#             }


#         # ----------------------------------------------------
#         # Quantity is known, but unit is NOT known.
#         #
#         # IMPORTANT:
#         # KEEP THE QUANTITY.
#         # ----------------------------------------------------

#         if quantity is not None:

#             return {
#                 "spoken_name":
#                     spoken_name,

#                 "search_name":
#                     spoken_name,

#                 "quantity":
#                     quantity,

#                 "unit":
#                     "unknown",

#                 "search_mode":
#                     "related_products",
#             }


#         # ----------------------------------------------------
#         # Product only
#         # ----------------------------------------------------

#         return {
#             "spoken_name":
#                 spoken_name,

#             "search_name":
#                 spoken_name,

#             "quantity":
#                 None,

#             "unit":
#                 "unknown",

#             "search_mode":
#                 "related_products",
#         }


#     # ========================================================
#     # PRODUCT-ONLY EMERGENCY FALLBACK
#     # ========================================================

#     def _extract_products_only(
#         self,
#         transcript: str,
#     ):

#         schema = {
#             "type": "object",
#             "properties": {
#                 "products": {
#                     "type": "array",
#                     "items": {
#                         "type": "string"
#                     },
#                 }
#             },
#             "required": [
#                 "products"
#             ],
#         }

#         response = self.llm.create_chat_completion(
#             messages=[
#                 {
#                     "role": "system",
#                     "content": """
# Extract only grocery product names from the speech.

# Keep natural multi-word grocery names together.

# Do not include quantities.
# Do not include units.

# Do not translate Tamil.
# Do not transliterate Tamil.

# Do not invent products.

# Return JSON only:

# {
#   "products": ["..."]
# }

# /no_think
# """,
#                 },
#                 {
#                     "role": "user",
#                     "content": transcript,
#                 },
#             ],
#             response_format={
#                 "type": "json_object",
#                 "schema": schema,
#             },
#             temperature=0.0,
#             max_tokens=250,
#         )

#         content = (
#             response
#             .get(
#                 "choices",
#                 [{}],
#             )[0]
#             .get(
#                 "message",
#                 {},
#             )
#             .get(
#                 "content",
#                 "",
#             )
#         )

#         return json.loads(
#             str(content).strip()
#         )


#     # ========================================================
#     # CONVERT QWEN RESULT -> API RESULT
#     # ========================================================

#     def _normalize_result(
#         self,
#         result: Dict[str, Any],
#     ) -> Dict[str, List[Dict[str, Any]]]:

#         final_items = []

#         raw_items = result.get(
#             "items",
#             [],
#         )

#         if not isinstance(
#             raw_items,
#             list,
#         ):
#             raw_items = []


#         for item in raw_items:

#             if not isinstance(
#                 item,
#                 dict,
#             ):
#                 continue


#             spoken_name = str(
#                 item.get(
#                     "spoken_name",
#                     "",
#                 )
#             ).strip()


#             if not spoken_name:
#                 continue


#             quantity = self._parse_quantity(
#                 item.get(
#                     "quantity"
#                 )
#             )


#             unit = str(
#                 item.get(
#                     "unit",
#                     "unknown",
#                 )
#             ).strip().lower()


#             if not unit:
#                 unit = "unknown"


#             final_items.append(
#                 self._build_item(
#                     spoken_name=spoken_name,
#                     quantity=quantity,
#                     unit=unit,
#                 )
#             )


#         return {
#             "items":
#                 final_items
#         }


#     # ========================================================
#     # MAIN PARSER
#     # ========================================================

#     def parse(
#         self,
#         transcript: str,
#     ):

#         transcript = str(
#             transcript or ""
#         ).strip()


#         if not transcript:

#             return {
#                 "items": []
#             }


#         # ----------------------------------------------------
#         # PASS 1
#         # ----------------------------------------------------

#         try:

#             draft = self._generate(
#                 transcript
#             )

#         except Exception as error:

#             print(
#                 "Main Qwen parse failed:",
#                 error,
#                 flush=True,
#             )

#             return self._fallback(
#                 transcript
#             )


#         # ----------------------------------------------------
#         # PASS 2
#         #
#         # Important because a 1.7B model can occasionally:
#         #
#         # - split multi-word names
#         # - attach quantity to wrong item
#         # - invent a unit
#         #
#         # The audit sees the ORIGINAL transcript again.
#         # ----------------------------------------------------

#         try:

#             audited = self._audit(
#                 transcript=transcript,
#                 draft=draft,
#             )

#             result = audited

#         except Exception as error:

#             print(
#                 "Qwen audit failed; "
#                 "using first parse:",
#                 error,
#                 flush=True,
#             )

#             result = draft


#         return self._normalize_result(
#             result
#         )


#     # ========================================================
#     # FALLBACK
#     # ========================================================

#     def _fallback(
#         self,
#         transcript: str,
#     ):

#         try:

#             product_result = (
#                 self._extract_products_only(
#                     transcript
#                 )
#             )


#             items = []


#             for product in product_result.get(
#                 "products",
#                 [],
#             ):

#                 product = str(
#                     product or ""
#                 ).strip()

#                 if not product:
#                     continue


#                 items.append(
#                     self._build_item(
#                         spoken_name=product,
#                         quantity=None,
#                         unit="unknown",
#                     )
#                 )


#             return {
#                 "items":
#                     items
#             }


#         except Exception as error:

#             print(
#                 "Fallback parser failed:",
#                 error,
#                 flush=True,
#             )

#             return {
#                 "items": []
#             }


# # ============================================================
# # SINGLE GLOBAL INSTANCE
# # ============================================================

# grocery_parser = GroceryParser()

















# grocery_parser deterministic-number V3
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from llama_cpp import Llama


MODEL_PATH = (
    "/home/hari/voicesearch_ai/models/"
    "Qwen3-1.7B-Q4_K_M.gguf"
)


Quantity = Optional[Union[int, float]]
Span = Tuple[int, int]


# =============================================================================
# DETERMINISTIC NUMBER / MEASUREMENT NORMALIZATION
# =============================================================================
#
# Qwen is still used for language understanding, product boundaries and
# difficult ASR cases.  Numeric arithmetic itself is deterministic whenever we
# can understand the number safely.  This prevents a later LLM call from
# changing correct Tamil values such as பதினெட்டு=18, இருநூறு=200 or
# ஐநூறு=500.
# =============================================================================

_TAMIL_NUMBER_EXACT: Dict[str, Union[int, float]] = {
    # 0-10 + common colloquial forms
    "பூஜ்ஜியம்": 0,
    "சுழியம்": 0,
    "ஒன்று": 1,
    "ஒரு": 1,
    "ஒன்னு": 1,
    "ஒண்ணு": 1,
    "இரண்டு": 2,
    "இரு": 2,
    "ரெண்டு": 2,
    "ரெண்ட": 2,
    "மூன்று": 3,
    "மூணு": 3,
    "நான்கு": 4,
    "நாலு": 4,
    "ஐந்து": 5,
    "அஞ்சு": 5,
    "ஆறு": 6,
    "ஏழு": 7,
    "எட்டு": 8,
    "ஒன்பது": 9,
    "ஒம்பது": 9,
    "பத்து": 10,

    # 11-19
    "பதினொன்று": 11,
    "பதினொன்னு": 11,
    "பன்னிரண்டு": 12,
    "பனிரெண்டு": 12,
    "பதிமூன்று": 13,
    "பதின்மூன்று": 13,
    "பதினான்கு": 14,
    "பதினைந்து": 15,
    "பதினாறு": 16,
    "பதினேழு": 17,
    "பதினெட்டு": 18,
    "பத்தொன்பது": 19,
    "பத்தொம்பது": 19,

    # tens
    "இருபது": 20,
    "முப்பது": 30,
    "நாற்பது": 40,
    "நாப்பது": 40,
    "ஐம்பது": 50,
    "அம்பது": 50,
    "ம்பது": 50,  # common dropped-leading-vowel ASR form
    "அறுபது": 60,
    "எழுபது": 70,
    "எண்பது": 80,
    "தொண்ணூறு": 90,
    "தொன்னூறு": 90,

    # hundreds
    "நூறு": 100,
    "நூற்று": 100,
    "நூத்த": 100,
    "நூத்து": 100,
    "இருநூறு": 200,
    "இநூறு": 200,  # observed ASR contraction of இருநூறு
    "ரெண்டுநூறு": 200,
    "இருநூற்று": 200,
    "முந்நூறு": 300,
    "முன்னூறு": 300,
    "மூன்றுநூறு": 300,
    "நானூறு": 400,
    "நான்குநூறு": 400,
    "ஐநூறு": 500,
    "ஐந்நூறு": 500,
    "அஞ்சுநூறு": 500,
    "அறுநூறு": 600,
    "எழுநூறு": 700,
    "எண்ணூறு": 800,
    "எட்டுநூறு": 800,
    "தொள்ளாயிரம்": 900,

    # thousands
    "ஆயிரம்": 1000,
    "ஆயிரத்து": 1000,
    "ஒராயிரம்": 1000,
    "ஓராயிரம்": 1000,
    "இரண்டாயிரம்": 2000,
    "ரெண்டாயிரம்": 2000,
    "மூவாயிரம்": 3000,
    "மூன்றாயிரம்": 3000,
    "நான்காயிரம்": 4000,
    "ஐந்தாயிரம்": 5000,
    "ஆறாயிரம்": 6000,
    "ஏழாயிரம்": 7000,
    "எட்டாயிரம்": 8000,
    "ஒன்பதாயிரம்": 9000,

    "ஜீரோ": 0, "சீரோ": 0, "ஸீரோ": 0,
        "ஒன்": 1, "வன்": 1,
        "டூ": 2, "டூ": 2, "டூவ்": 2,
        "த்ரீ": 3, "த்ரி": 3, "திரீ": 3,
        "ஃபோர்": 4, "போர்": 4, "ஃபார்": 4,
        "ஃபைவ்": 5, "பைவ்": 5, "பைவு": 5,
        "சிக்ஸ்": 6, "ஸிக்ஸ்": 6,
        "செவன்": 7, "ஸெவன்": 7,
        "எய்ட்": 8, "எயிட்": 8, "ஏட்": 8,
        "நைன்": 9, "நயன்": 9,
        "டென்": 10, "தென்": 10,
        "லெவன்": 11, "எலெவன்": 11, "இலெவன்": 11,
        "ட்வெல்வ்": 12, "டுவெல்வ்": 12,
        "தர்டீன்": 13, "தெர்டீன்": 13,
        "ஃபோர்டீன்": 14, "போர்டீன்": 14,
        "ஃபிஃப்டீன்": 15, "பிஃப்டீன்": 15,
        "சிக்ஸ்டீன்": 16,
        "செவன்டீன்": 17,
        "எய்டீன்": 18, "எய்ட்டீன்": 18,
        "நைன்டீன்": 19,
    
        # tens
        "ட்வென்டி": 20, "டுவென்டி": 20, "ட்வண்டி": 20,
        "தர்டி": 30, "தெர்டி": 30,
        "ஃபோர்டி": 40, "போர்டி": 40,
        "ஃபிஃப்டி": 50, "பிஃப்டி": 50, "பிப்டி": 50,
        "சிக்ஸ்டி": 60,
        "செவன்டி": 70,
        "எய்டி": 80, "எய்ட்டி": 80,
        "நைன்டி": 90,
    
        # scales
        "ஹண்ட்ரட்": 100, "ஹண்ட்ரெட்": 100, "ஹன்ட்ரட்": 100,
        "தவுசண்ட்": 1000, "தௌசண்ட்": 1000, "தவுசன்ட்": 1000,"ஹண்டரட்": 100, "ஹண்ட்ரெட்": 100, "ஹன்ட்ரட்": 100,
    
        # fractions commonly spoken in English
        "ஹாஃப்": 0.5, "ஹாப்": 0.5,
        "குவார்டர்": 0.25, "க்வார்டர்": 0.25,

    # observed compact speech/ASR forms
    "இருநூத்தம்பது": 250,
    "இருநூத்துஐம்பது": 250,
    "இருரநூத்தம்பது": 250,
    "இருநூற்றம்பது": 250,
    "ஐம்பத்தொன்பது": 59,
    "அம்பத்தொன்பது": 59,
    "ம்பத்தொன்பது": 59,
}

_TAMIL_FRACTIONS: Dict[str, float] = {
    "அரை": 0.5,
    "அர": 0.5,
    "half": 0.5,
    "கால்": 0.25,
    "கா்": 0.25,   # IndicConformer can drop the final ல்
    "quarter": 0.25,
    "முக்கால்": 0.75,
    "ஒன்றரை": 1.5,
    "ஒன்னரை": 1.5,
    "ரெண்டரை": 2.5,
    "இரண்டரை": 2.5,
    "மூன்றரை": 3.5,
}

_TANGLISH_NUMBER_EXACT: Dict[str, Union[int, float]] = {
    "zero": 0,
    "one": 1,
    "onnu": 1,
    "two": 2,
    "rendu": 2,
    "three": 3,
    "moonu": 3,
    "four": 4,
    "naalu": 4,
    "five": 5,
    "anju": 5,
    "six": 6,
    "aaru": 6,
    "seven": 7,
    "ezhu": 7,
    "eight": 8,
    "ettu": 8,
    "nine": 9,
    "onbadhu": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "ambadhu": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "nooru": 100,
    "irunooru": 200,
    "ainooru": 500,
    "aayiram": 1000,
    "thousand": 1000,
    "arai": 0.5,
    "kaal": 0.25,
    "onnara": 1.5,
    "rendara": 2.5,
}



_TAMIL_TENS_PREFIXES: Tuple[Tuple[str, int], ...] = (
    ("தொண்ணூற்று", 90),
    ("தொன்னூற்று", 90),
    ("இருபத்து", 20),
    ("இருபத்தி", 20),
    ("இருபத்த", 20),
    ("முப்பத்து", 30),
    ("முப்பத்தி", 30),
    ("முப்பத்த", 30),
    ("நாற்பத்து", 40),
    ("நாற்பத்தி", 40),
    ("நாற்பத்த", 40),
    ("நாப்பத்து", 40),
    ("நாப்பத்த", 40),
    ("ஐம்பத்து", 50),
    ("ஐம்பத்தி", 50),
    ("ஐம்பத்த", 50),
    ("அம்பத்து", 50),
    ("அம்பத்தி", 50),
    ("அம்பத்த", 50),
    ("ம்பத்து", 50),
    ("ம்பத்த", 50),
    ("அறுபத்து", 60),
    ("அறுபத்தி", 60),
    ("அறுபத்த", 60),
    ("எழுபத்து", 70),
    ("எழுபத்தி", 70),
    ("எழுபத்த", 70),
    ("எண்பத்து", 80),
    ("எண்பத்தி", 80),
    ("எண்பத்த", 80),
)

_TAMIL_HUNDRED_PREFIXES: Tuple[Tuple[str, int], ...] = (
    ("இருநூற்று", 200),
    ("இருநூத்து", 200),
    ("இருநூத்த", 200),
    ("ரெண்டுநூற்று", 200),
    ("முன்னூற்று", 300),
    ("முந்நூற்று", 300),
    ("நானூற்று", 400),
    ("ஐந்நூற்று", 500),
    ("ஐநூற்று", 500),
    ("அறுநூற்று", 600),
    ("எழுநூற்று", 700),
    ("எண்ணூற்று", 800),
    ("நூற்று", 100),
    ("நூத்து", 100),
    ("நூத்த", 100),
)

_TAMIL_UNIT_REMAINDER_FIXES: Tuple[Tuple[str, str], ...] = (
    ("ம்பத்த", "ஐம்பத்த"),
    ("ம்பது", "அம்பது"),
    ("ொன்று", "ஒன்று"),
    ("ிரண்டு", "இரண்டு"),
    ("ரண்டு", "இரண்டு"),
    ("ுமூன்று", "மூன்று"),
    ("ுநான்கு", "நான்கு"),
    ("ைந்து", "ஐந்து"),
    ("ாறு", "ஆறு"),
    ("ேழு", "ஏழு"),
    ("ெட்டு", "எட்டு"),
    ("ொன்பது", "ஒன்பது"),
    ("ொம்பது", "ஒம்பது"),
)

# canonical unit, multiplier applied to the spoken numeric amount
_UNIT_SPECS: Dict[str, Tuple[str, float]] = {
    # weight
    "kg": ("g", 1000.0),
    "kgs": ("g", 1000.0),
    "kilo": ("g", 1000.0),
    "kilos": ("g", 1000.0),
    "kilogram": ("g", 1000.0),
    "kilograms": ("g", 1000.0),
    "கிலோ": ("g", 1000.0),
    "கிலோகிராம்": ("g", 1000.0),
    "கிலோகிராம்கள்": ("g", 1000.0),
    "g": ("g", 1.0),
    "gm": ("g", 1.0),
    "gms": ("g", 1.0),
    "gram": ("g", 1.0),
    "grams": ("g", 1.0),
    "கிராம்": ("g", 1.0),
    "கிராம்கள்": ("g", 1.0),

    # liquid volume
    "l": ("ml", 1000.0),
    "ltr": ("ml", 1000.0),
    "litre": ("ml", 1000.0),
    "litres": ("ml", 1000.0),
    "liter": ("ml", 1000.0),
    "liters": ("ml", 1000.0),
    "லிட்டர்": ("ml", 1000.0),
    "லீட்டர்": ("ml", 1000.0),
    "ml": ("ml", 1.0),
    "millilitre": ("ml", 1.0),
    "millilitres": ("ml", 1.0),
    "milliliter": ("ml", 1.0),
    "milliliters": ("ml", 1.0),
    "மில்லிலிட்டர்": ("ml", 1.0),
    "மில்லிலீட்டர்": ("ml", 1.0),

    # package / count
    "packet": ("packet", 1.0),
    "packets": ("packet", 1.0),
    "pack": ("packet", 1.0),
    "pkt": ("packet", 1.0),
    "பாக்கெட்": ("packet", 1.0),
    "பேக்கெட்": ("packet", 1.0),
    "bottle": ("bottle", 1.0),
    "bottles": ("bottle", 1.0),
    "பாட்டில்": ("bottle", 1.0),
    "piece": ("pcs", 1.0),
    "pieces": ("pcs", 1.0),
    "pcs": ("pcs", 1.0),
    "pc": ("pcs", 1.0),
    "பீஸ்": ("pcs", 1.0),
    "box": ("box", 1.0),
    "boxes": ("box", 1.0),
    "பெட்டி": ("box", 1.0),
    "dozen": ("dozen", 1.0),
    "டஜன்": ("dozen", 1.0),
}


def _number_norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u200c", "").replace("\u200d", "")
    text = text.strip().lower()
    text = re.sub(r"^[,;:.!?]+|[,;:.!?]+$", "", text)
    return text


def _normalize_tamil_remainder(text: str) -> str:
    value = _number_norm(text)
    for prefix, replacement in _TAMIL_UNIT_REMAINDER_FIXES:
        if value.startswith(prefix):
            return replacement + value[len(prefix):]
    return value


def _parse_tamil_number_token(token: str) -> Quantity:
    value = _number_norm(token)
    if not value:
        return None

    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        number = float(value)
        return int(number) if number.is_integer() else number

    if value in _TAMIL_FRACTIONS:
        return _TAMIL_FRACTIONS[value]

    if value in _TAMIL_NUMBER_EXACT:
        number = _TAMIL_NUMBER_EXACT[value]
        return int(number) if float(number).is_integer() else float(number)

    # 2,000 / 3,000 ... as one Tamil token, e.g. இரண்டாயிரம்.
    if value.endswith("ஆயிரம்") and value != "ஆயிரம்":
        prefix = value[:-len("ஆயிரம்")]
        prefix_value = _parse_tamil_number_token(prefix)
        if prefix_value is not None and 0 < float(prefix_value) < 100:
            result = float(prefix_value) * 1000.0
            return int(result) if result.is_integer() else result

    # Hundreds with a following compact remainder, e.g. இருநூத்தம்பது.
    for prefix, base in _TAMIL_HUNDRED_PREFIXES:
        if value.startswith(prefix) and len(value) > len(prefix):
            remainder = _normalize_tamil_remainder(value[len(prefix):])
            remainder_value = _parse_tamil_number_token(remainder)
            if (
                remainder_value is not None
                and 0 < float(remainder_value) < 100
            ):
                result = float(base) + float(remainder_value)
                return int(result) if result.is_integer() else result

    # 21..99 compact forms.  We only compose a valid 1..9 remainder.
    for prefix, base in _TAMIL_TENS_PREFIXES:
        if value.startswith(prefix) and len(value) > len(prefix):
            remainder = _normalize_tamil_remainder(value[len(prefix):])
            remainder_value = _parse_tamil_number_token(remainder)
            if (
                remainder_value is not None
                and 0 < float(remainder_value) < 10
            ):
                result = float(base) + float(remainder_value)
                return int(result) if result.is_integer() else result

    return None


def _parse_english_number_phrase(text: str) -> Quantity:
    """
    Parse English / Tanglish / Tamil-script-English number phrases.

    Examples:
        five hundred                  -> 500
        பைவ் ஹண்ட்ரெட்                -> 500

        two fifty                     -> 250
        டூ பிஃப்டி                    -> 250

        one fifty                     -> 150
        ஒன் பிஃப்டி                   -> 150

        three hundred                 -> 300
        த்ரீ ஹண்ட்ரெட்                -> 300

        one hundred fifty             -> 150
        ஒன் ஹண்ட்ரெட் பிஃப்டி         -> 150

        one thousand five hundred     -> 1500
        ஒன் தவுசண்ட் பைவ் ஹண்ட்ரெட்   -> 1500
    """

    value = _number_norm(text)

    if not value:
        return None

    parts = [
        p
        for p in re.split(
            r"[\s-]+",
            value,
        )
        if p
    ]

    if not parts:
        return None


    # ---------------------------------------------------------
    # SCALE WORDS
    # ---------------------------------------------------------

    hundred_words = {
        "hundred",

        "ஹண்ட்ரட்",
        "ஹண்ட்ரெட்",
        "ஹன்ட்ரட்",
        "ஹண்டரட்",
    }

    thousand_words = {
        "thousand",

        "தவுசண்ட்",
        "தௌசண்ட்",
        "தவுசன்ட்",
    }

    conjunction_words = {
        "and",
        "அண்ட்",
    }


    # ---------------------------------------------------------
    # CONVERT ONE TOKEN
    # ---------------------------------------------------------

    def token_value(
        part: str,
    ) -> Quantity:

        # English / Tanglish
        if part in _TANGLISH_NUMBER_EXACT:

            number = (
                _TANGLISH_NUMBER_EXACT[
                    part
                ]
            )

            return (
                int(number)
                if float(number).is_integer()
                else float(number)
            )


        # Tamil +
        # Tamil-script English ASR
        #
        # Examples:
        #
        # பைவ்    -> 5
        # பிஃப்டி -> 50
        #
        number = (
            _parse_tamil_number_token(
                part
            )
        )

        if number is None:
            return None

        return (
            int(number)
            if float(number).is_integer()
            else float(number)
        )


    # ---------------------------------------------------------
    # SINGLE TOKEN
    # ---------------------------------------------------------

    if len(parts) == 1:

        return token_value(
            parts[0]
        )


    # ---------------------------------------------------------
    # SPOKEN GROCERY SHORT FORM
    #
    # two fifty      -> 250
    # டூ பிஃப்டி     -> 250
    #
    # one fifty      -> 150
    # ஒன் பிஃப்டி    -> 150
    #
    # three twenty   -> 320
    # த்ரீ ட்வென்டி  -> 320
    # ---------------------------------------------------------

    if len(parts) == 2:

        first = token_value(
            parts[0]
        )

        second = token_value(
            parts[1]
        )

        if (
            first is not None
            and second is not None

            and 1 <= float(first) <= 9

            and float(first).is_integer()

            and 20 <= float(second) <= 90

            and float(second) % 10 == 0
        ):

            result = (
                float(first) * 100
                + float(second)
            )

            return int(result)


    # ---------------------------------------------------------
    # FULL NUMBER PHRASE PARSER
    #
    # IMPORTANT:
    #
    # five hundred
    #
    # MUST BE:
    #
    # 5 * 100 = 500
    #
    # NOT:
    #
    # 5 + 100 = 105
    # ---------------------------------------------------------

    total = 0.0
    current = 0.0

    saw_number = False


    for part in parts:

        # ---------------------------------
        # ignore "and"
        # ---------------------------------

        if part in conjunction_words:
            continue


        # ---------------------------------
        # HUNDRED SCALE
        #
        # five hundred
        #
        # 5 * 100
        # ---------------------------------

        if part in hundred_words:

            current = (
                max(
                    current,
                    1.0,
                )
                * 100.0
            )

            saw_number = True

            continue


        # ---------------------------------
        # THOUSAND SCALE
        #
        # two thousand
        #
        # 2 * 1000
        # ---------------------------------

        if part in thousand_words:

            total += (
                max(
                    current,
                    1.0,
                )
                * 1000.0
            )

            current = 0.0

            saw_number = True

            continue


        # ---------------------------------
        # NORMAL NUMBER TOKEN
        # ---------------------------------

        number = token_value(
            part
        )

        if number is None:
            return None

        current += float(
            number
        )

        saw_number = True


    # ---------------------------------------------------------
    # FINAL RESULT
    # ---------------------------------------------------------

    if not saw_number:
        return None

    result = (
        total
        + current
    )

    if result <= 0:
        return None


    if result.is_integer():
        return int(result)

    return result

def _parse_deterministic_quantity_text(text: str) -> Quantity:
    value = _number_norm(text)
    if not value:
        return None

    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        number = float(value)
        return int(number) if number.is_integer() else number

    # One Tamil token first.
    single = _parse_tamil_number_token(value)
    if single is not None:
        return single

    # English/Tanglish phrase.
    english = _parse_english_number_phrase(value)
    if english is not None:
        return english

    parts = [p for p in value.split() if p]
    if not parts:
        return None

    # Tamil multi-token composition such as:
    #   நூற்று ஐம்பது -> 150
    #   ஆயிரத்து ஐநூறு -> 1500
    #   இரண்டு ஆயிரம் -> 2000
    total = 0.0
    current = 0.0
    saw = False

    pure_hundred_scales = {
        "நூறு", "நூற்று", "நூத்து", "நூத்த",
    }
    pure_thousand_scales = {
        "ஆயிரம்", "ஆயிரத்து",
    }

    for part in parts:
        normalized = _number_norm(part)

        if normalized in pure_hundred_scales:
            current = max(current, 1.0) * 100.0
            saw = True
            continue

        if normalized in pure_thousand_scales:
            total += max(current, 1.0) * 1000.0
            current = 0.0
            saw = True
            continue

        number = _parse_tamil_number_token(normalized)
        if number is None:
            return None

        current += float(number)
        saw = True

    if not saw:
        return None

    result = total + current
    if result <= 0:
        return None
    return int(result) if result.is_integer() else result


def _unit_spec(text: str) -> Optional[Tuple[str, float]]:
    value = _number_norm(text)
    if not value:
        return None

    compact = re.sub(r"\s+", "", value)
    direct = _UNIT_SPECS.get(value) or _UNIT_SPECS.get(compact)
    if direct is not None:
        return direct

    # Common two-token Tamil ml phrase after whitespace removal.
    if compact in {"மில்லிலிட்டர்", "மில்லிலீட்டர்"}:
        return ("ml", 1.0)

    return None


def _parse_merged_measurement_token(token: str) -> Optional[Tuple[Quantity, str]]:
    """Parse one ASR token that accidentally merged quantity + unit."""
    value = _number_norm(token)
    if not value:
        return None

    # Longest aliases first so "kilogram" wins before shorter endings.
    for unit_text, (canonical_unit, multiplier) in sorted(
        _UNIT_SPECS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if not value.endswith(unit_text) or value == unit_text:
            continue

        prefix = value[:-len(unit_text)].strip()
        if not prefix:
            continue

        quantity = _parse_deterministic_quantity_text(prefix)

        # Tamil sandhi can leave a linking க் before கிலோ, for example
        # அரைக்கிலோ -> அரைக் + கிலோ.  IndicConformer can similarly emit
        # கா்க்கிலோ -> கா்க் + கிலோ for கால் கிலோ.
        if quantity is None and prefix.endswith("க்"):
            quantity = _parse_deterministic_quantity_text(prefix[:-len("க்")])
        if quantity is None:
            continue

        final_quantity = float(quantity) * multiplier
        if final_quantity <= 0:
            continue

        normalized_quantity: Quantity = (
            int(final_quantity)
            if final_quantity.is_integer()
            else final_quantity
        )
        return normalized_quantity, canonical_unit

    return None


def _deterministic_measurement(
    quantity_text: str,
    explicit_unit_text: str,
) -> Optional[Tuple[Quantity, str]]:
    """Return a safe deterministic quantity/unit pair when possible."""
    quantity_text = _number_norm(quantity_text)
    explicit_unit_text = _number_norm(explicit_unit_text)

    if not quantity_text:
        return None

    if not explicit_unit_text:
        merged = _parse_merged_measurement_token(quantity_text)
        if merged is not None:
            return merged

    quantity = _parse_deterministic_quantity_text(quantity_text)
    if quantity is None:
        return None

    if not explicit_unit_text:
        return quantity, "unknown"

    spec = _unit_spec(explicit_unit_text)
    if spec is None:
        return None

    canonical_unit, multiplier = spec
    final_quantity = float(quantity) * multiplier
    if final_quantity <= 0:
        return None

    normalized_quantity: Quantity = (
        int(final_quantity)
        if final_quantity.is_integer()
        else final_quantity
    )

    return normalized_quantity, canonical_unit


# =============================================================================
# PASS 1 — TOKEN SEMANTICS ONLY
# =============================================================================
#
# This stage does NOT decide product boundaries and does NOT create product
# names. It only decides whether every transcript token is:
#
#   number    -> spoken numeric expression / fraction / count
#   unit      -> explicitly spoken measurement/package/count unit
#   word      -> ordinary lexical word (normally part of a product name)
#   separator -> connector/filler/punctuation-like speech token
#
# Two independent passes are run. If they disagree, a focused tie-break call
# decides that exact token in context.
#
# This is deliberately much simpler than asking one small model to decide
# products + boundaries + quantities + units at the same time.
# =============================================================================

TOKEN_ROLE_PROMPT_A = r"""
You are a TOKEN SEMANTICS classifier for grocery voice search.

The customer may speak:
- Tamil
- colloquial/regional Tamil
- imperfect ASR Tamil
- Tanglish
- English
- mixed Tamil/English
- digits

You receive the ORIGINAL transcript and numbered whitespace tokens.

For EVERY token index exactly once, assign ONE role:

"number"
    The token itself is a spoken numeric expression or part of a multi-token
    numeric expression. This includes colloquial/formal Tamil number words,
    Tanglish/English number words, digits, fractions and imperfect-ASR forms
    that clearly represent a number in context.

"unit"
    The token itself explicitly expresses a measurement/package/count unit:
    weight, volume, packet, bottle, piece/count, box, dozen, etc.

"word"
    An ordinary lexical word. In this grocery-search context it is normally a
    product-name word.

"separator"
    Only a connector/filler/separator, not a product word, number, or unit.

IMPORTANT:
- Classify the TOKEN, not an arbitrary phrase around it.
- Never absorb the next product word into a number.
- Never absorb a number into a product.
- A product may have no quantity.
- Product words may be adjacent with no pause or "and".
- A real multi-word product is still multiple "word" tokens at this stage.
- Do NOT decide whether adjacent product words belong together yet.
- Do NOT translate, correct, or invent transcript text.
- Return EVERY token index exactly once.

Example principle:
tokens:
0: chicken
1: masala
2: fifty
3: peas
4: two-hundred

roles:
0 word
1 word
2 number
3 word
4 number

Return JSON only:
{
  "tokens": [
    {"index": 0, "role": "word"}
  ]
}

/no_think
"""


TOKEN_ROLE_PROMPT_B = r"""
Independently classify EVERY numbered transcript token for grocery voice search.

Allowed roles:
- number
- unit
- word
- separator

NUMBER:
A spoken number, count, fraction, compound-number component, digit, or an
imperfect-ASR token that clearly means a number in this sentence.

UNIT:
An explicitly spoken measurement/package/count unit only.

WORD:
A normal lexical word, usually a product-name word.

SEPARATOR:
Only a connector/filler.

STRICT RULES:
1. Return one record for every token index.
2. Never classify a normal product word as part of the previous number.
3. Never classify a number word as a grocery product word.
4. Multi-word product names are NOT joined here. Their tokens remain "word".
5. Do not require digits; spoken Tamil number words are numbers.
6. Understand colloquial/regional Tamil and plausible ASR corruption
   semantically from context.
7. Do not translate or rewrite anything.

Return JSON only:
{
  "tokens": [
    {"index": 0, "role": "word"}
  ]
}

/no_think
"""


TOKEN_TIE_BREAK_PROMPT = r"""
You are resolving ONE disputed transcript token.

Choose exactly one role:
- number
- unit
- word
- separator

Use the ORIGINAL transcript and local context.

Important:
- "number" means the token itself expresses a numeric value/fraction/count or
  is clearly an imperfect-ASR number form.
- "unit" means the token itself is an explicitly spoken measurement/package
  unit.
- "word" means an ordinary lexical/product-name word.
- Do not let a nearby number swallow a product word.
- Do not turn a number word into a product.
- Do not translate/correct the token.

Return JSON only:
{
  "role": "number"
}

/no_think
"""


NUMBER_RESCUE_PROMPT = r"""
You are a focused SPOKEN-NUMBER detector for grocery voice search.

The transcript may contain Tamil, colloquial/regional Tamil, imperfect ASR
Tamil, Tanglish, English, mixed speech, or digits.

You receive the ORIGINAL transcript and numbered tokens.

Your only job is to identify tokens that genuinely function as a NUMERIC
QUANTITY in this sentence.

A numeric token may be:
- a whole spoken number
- one component of a multi-token compound number
- a fraction
- a colloquial Tamil number
- a merged/contracted spoken-number form
- an imperfect-ASR spelling of a spoken number
- an English/Tanglish number
- digits

Important:
- Use sentence context and meaning, not exact spelling.
- A token after a grocery product can be a quantity even when ASR spelling is
  imperfect.
- Never classify an actual measurement word (gram, kilo, litre, packet, piece,
  bottle, etc.) as a number.
- Never classify a genuine product-name word as a number.
- Do not treat a digit inside an alphanumeric brand/product name as a quantity.
- Do not invent a number merely because a product has no quantity.
- If a token is numeric, return the numeric value that token contributes.
- If a multi-token number is spoken, each numeric component may be returned;
  the later measurement parser will combine the full contiguous phrase.
- Return ONLY tokens you are confident are numeric.
- Do not translate or rewrite transcript tokens.

Examples of number semantics only:
- Tamil/colloquial speech meaning 18 -> numeric
- Tamil/colloquial speech meaning 50 -> numeric
- Tamil/colloquial speech meaning 100 -> numeric
- Tamil/colloquial speech meaning 250 -> numeric
- imperfect ASR forms of those spoken quantities are still numeric when the
  context clearly supports that reading

Return JSON only:
{
  "numbers": [
    {"index": 1, "quantity": "50"}
  ]
}

/no_think
"""


SINGLE_NUMERIC_TOKEN_PROMPT = r"""
You validate ONE exact transcript token for grocery voice search.

The speech may be Tamil, colloquial/regional Tamil, imperfect ASR Tamil,
Tanglish, English, mixed speech, or digits.

Decide whether the TARGET TOKEN itself communicates a numeric quantity.

The token can be:
- a whole number
- a fraction such as half or quarter
- a colloquial/contracted spoken number
- an imperfect-ASR form of a spoken number
- a token where ASR accidentally MERGED a number/fraction and a unit together

Important:
- A token meaning only a measurement unit is NOT a numeric quantity.
- A normal grocery/product word is NOT a numeric quantity.
- Do not invent a number just because a product appears nearby.
- Use the ORIGINAL transcript and neighboring tokens to recover plausible
  ASR corruption.
- This is semantic recognition, not exact-spelling lookup.

If the token is a numeric quantity WITHOUT its own unit:
- is_quantity = true
- quantity = its mathematical value
- unit = "unknown"
- contains_unit = false

Examples of mathematical values:
- a spoken whole number meaning 250 -> "250"
- a spoken whole number meaning 1500 -> "1500"
- half by itself -> "0.5"
- quarter by itself -> "0.25"

If ASR merged quantity + unit into this ONE token:
- is_quantity = true
- contains_unit = true
- normalize the final retail measurement:
  kg/kilogram -> grams ("g")
  litre/liter -> millilitres ("ml")
  grams -> "g"
  ml -> "ml"
  explicit package/count -> packet/bottle/pcs/box/dozen as appropriate
- quantity must be the normalized final amount.
  A token semantically meaning quarter kilogram is 250 g.
  A token semantically meaning half litre is 500 ml.

If it is not a numeric quantity:
- is_quantity = false
- quantity = ""
- unit = "unknown"
- contains_unit = false

Return JSON only:
{
  "is_quantity": true,
  "quantity": "250",
  "unit": "unknown",
  "contains_unit": false
}

/no_think
"""


# =============================================================================
# PASS 2 — PRODUCT BOUNDARIES ONLY
# =============================================================================
#
# At this point number/unit tokens are already removed from product coverage.
# We only ask whether directly adjacent WORD tokens belong to one natural
# product name or two separate products.
# =============================================================================

BOUNDARY_PROMPT_A = r"""
You decide PRODUCT BOUNDARIES between adjacent product-word tokens.

The transcript is grocery voice search and may contain Tamil, colloquial Tamil,
Tanglish, English, mixed speech, and imperfect ASR.

You receive candidate adjacent WORD pairs. For every pair return:

"same_product"
    only when the two adjacent words naturally belong to ONE purchasable
    product name in this context.

"new_product"
    when the right word starts another requested product.

Examples of principle:
- a spice/product compound such as "chicken masala" can be one product
- two separately purchasable grocery items spoken continuously are separate

IMPORTANT:
- Customers do NOT need pauses, commas, or "and" between products.
- Do not merge merely because words are adjacent.
- Preserve genuine multi-word product names.
- Judge only the supplied pair in the full transcript context.
- Return every pair id exactly once.

Return JSON only:
{
  "boundaries": [
    {"pair_id": 0, "relation": "same_product"}
  ]
}

/no_think
"""


BOUNDARY_PROMPT_B = r"""
Independently audit adjacent grocery product-word pairs.

For each supplied pair choose exactly:
- same_product
- new_product

Use SAME_PRODUCT only if the two words clearly form one natural purchasable
product name in the sentence.

Otherwise choose NEW_PRODUCT.

There may be several products spoken continuously without pauses or connector
words. Adjacency alone never proves one product.

Do not translate, correct, or invent product words.

Return every pair id exactly once as JSON:
{
  "boundaries": [
    {"pair_id": 0, "relation": "new_product"}
  ]
}

/no_think
"""


BOUNDARY_FINAL_VERIFY_PROMPT = r"""
You are the FINAL semantic verifier for ONE boundary between two adjacent
grocery product-word tokens.

Decide whether LEFT WORD + RIGHT WORD are ONE natural purchasable product name
in the ORIGINAL transcript, or whether RIGHT WORD starts a separate product.

Return exactly:
- "same_product"
- "new_product"

Use "same_product" when the two words together name or describe ONE item.
This includes ordinary compositional grocery names, not only famous/fixed names:
- descriptor/type/colour/flavour/preparation/ingredient + grocery noun
- noun + form/type words that together identify one product
- natural spice/masala/powder/oil/rice/dal/etc. compounds
- Tamil, English, Tanglish and mixed multi-word product names

Use "new_product" when the customer is actually listing two separately
requested products.

Important:
- Grocery lists often omit commas, pauses and the word "and".
- Adjacency alone is NOT enough to merge.
- But do NOT split a natural two-word product merely because each token could
  have an independent dictionary meaning.
- Judge the complete two-word phrase in the full transcript.
- Quantity/unit tokens have already been removed from product-word pairs.
- Do not translate, correct, or invent text.

Return JSON only:
{
  "relation": "same_product"
}

/no_think
"""


# =============================================================================
# PASS 3 — SEMANTIC QUANTITY CONVERSION
# =============================================================================

MEASUREMENT_PARSE_PROMPT = r"""
You convert already-identified SPOKEN QUANTITY PHRASES into numeric values.

You receive measurement rows. Each row contains:
- measurement_id
- quantity_text: exact transcript number words
- explicit_unit_text: exact explicitly spoken unit words, or empty

For EVERY row:

1. Understand quantity_text SEMANTICALLY.
   It may be:
   - formal Tamil
   - colloquial/regional Tamil
   - imperfect ASR Tamil
   - Tanglish
   - English
   - digits
   - multi-token compound numbers
   - fractions

2. Return the COMPLETE mathematical value as digits.
   This is NOT a finite lookup-table task.

3. If explicit_unit_text is present:
   normalize BOTH quantity and unit:
   - kilograms / kg -> grams, unit "g"
   - litres / liters / l -> millilitres, unit "ml"
   - grams -> "g"
   - ml -> "ml"
   - package/count units -> packet, bottle, pcs, box, dozen as appropriate

4. If explicit_unit_text is empty:
   return unit="unknown".
   Unit inference happens later from the product meaning.

5. Do not invent a quantity.
6. Do not use nearby product words as part of quantity_text.

Examples only illustrate semantics:
- Tamil word meaning fifty -> quantity "50"
- Tamil word meaning two hundred -> "200"
- imperfect ASR number form that clearly means two hundred -> "200"
- one litre -> quantity "1000", unit "ml"
- half kilogram -> quantity "500", unit "g"

Return every measurement_id exactly once.

JSON only:
{
  "measurements": [
    {
      "measurement_id": 0,
      "quantity": "50",
      "unit": "unknown"
    }
  ]
}

/no_think
"""


SINGLE_MEASUREMENT_PROMPT = r"""
Convert this one spoken quantity expression semantically.

Inputs:
- quantity_text
- explicit_unit_text (may be empty)

The quantity may be Tamil, colloquial/regional Tamil, imperfect ASR Tamil,
Tanglish, English, digits, compound numbers or fractions.

Return the complete numeric value.

If an explicit unit is present:
- kg -> grams / g
- litre/liter/l -> millilitres / ml
- gram -> g
- ml -> ml
- explicit package/count -> packet/bottle/pcs/box/dozen as appropriate

If no unit is explicitly spoken, return unit="unknown".

Do not infer a product unit here.

JSON only:
{
  "quantity": "50",
  "unit": "unknown"
}

/no_think
"""


# =============================================================================
# PASS 4 — NATURAL UNIT INFERENCE
# =============================================================================

UNIT_INFERENCE_PROMPT = r"""
You infer the NATURAL RETAIL MEASUREMENT UNIT for products whose customer
spoke a quantity but DID NOT speak a unit.

You receive:
- product_index
- product_name exactly as heard
- numeric quantity already parsed

For every row choose exactly one canonical unit:

- g
- ml
- packet
- bottle
- pcs
- box
- dozen
- unknown

Use product semantics and normal grocery retail measurement.

Examples of the principle:
- dry groceries/spices/powders commonly measured by weight -> g
- liquids commonly measured by volume -> ml
- products naturally requested as packets -> packet
- countable individual items -> pcs
- products naturally requested as bottles -> bottle
- boxed products -> box

IMPORTANT:
- There is NO hardcoded product-to-unit mapping.
- Infer semantically from the product.
- Do NOT change the customer's numeric quantity.
- Use unknown only when genuinely ambiguous.
- Do not translate or rename the product.

Return every product_index exactly once.

JSON only:
{
  "units": [
    {"product_index": 0, "unit": "g"}
  ]
}

/no_think
"""


SINGLE_UNIT_INFERENCE_PROMPT = r"""
Infer the natural retail measurement unit for this grocery/product.

Allowed:
g, ml, packet, bottle, pcs, box, dozen, unknown

The customer supplied a numeric quantity but no explicit unit.
Use product semantics and normal retail measurement.
Do not change the quantity.
Do not translate or rename the product.
Use unknown only when genuinely ambiguous.

JSON only:
{
  "unit": "g"
}

/no_think
"""


class GroceryParser:
    def __init__(self) -> None:
        print("Loading Qwen grocery parser...", flush=True)

        self.llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_threads=4,
            n_batch=128,
            verbose=False,
            seed=42,
        )

        print("Qwen grocery parser ready.", flush=True)

    # =========================================================================
    # BASIC HELPERS
    # =========================================================================

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = unicodedata.normalize(
            "NFKC",
            str(value or ""),
        )

        text = re.sub(
            r"[,;|\u3001]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    @classmethod
    def _tokenize(cls, transcript: str) -> List[str]:
        text = cls._normalize_text(transcript)

        if not text:
            return []

        return text.split()

    @staticmethod
    def _tokens_for_prompt(tokens: Sequence[str]) -> str:
        return "\n".join(
            f"{index}: {token}"
            for index, token in enumerate(tokens)
        )

    @staticmethod
    def _parse_quantity(value: Any) -> Quantity:
        text = str(value or "").strip()

        if not text:
            return None

        if not re.fullmatch(
            r"\d+(?:\.\d+)?",
            text,
        ):
            return None

        number = float(text)

        if number <= 0:
            return None

        if number.is_integer():
            return int(number)

        return number

    @staticmethod
    def _normalize_unit(value: Any) -> str:
        unit = str(
            value or "unknown"
        ).strip().lower()

        aliases = {
            "": "unknown",
            "unknown": "unknown",

            "g": "g",
            "gm": "g",
            "gms": "g",
            "gram": "g",
            "grams": "g",

            "ml": "ml",
            "millilitre": "ml",
            "millilitres": "ml",
            "milliliter": "ml",
            "milliliters": "ml",

            "packet": "packet",
            "packets": "packet",
            "pack": "packet",
            "packs": "packet",
            "pkt": "packet",

            "bottle": "bottle",
            "bottles": "bottle",

            "pc": "pcs",
            "pcs": "pcs",
            "piece": "pcs",
            "pieces": "pcs",
            "count": "pcs",

            "box": "box",
            "boxes": "box",

            "dozen": "dozen",
        }

        return aliases.get(
            unit,
            "unknown",
        )

    # =========================================================================
    # JSON SCHEMAS
    # =========================================================================

    @staticmethod
    def _token_roles_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tokens": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {
                                "type": "integer",
                            },
                            "role": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "index",
                            "role",
                        ],
                    },
                },
            },
            "required": [
                "tokens",
            ],
        }

    @staticmethod
    def _single_role_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                },
            },
            "required": [
                "role",
            ],
        }

    @staticmethod
    def _number_rescue_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "numbers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {
                                "type": "integer",
                            },
                            "quantity": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "index",
                            "quantity",
                        ],
                    },
                },
            },
            "required": [
                "numbers",
            ],
        }

    @staticmethod
    def _single_numeric_token_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "is_quantity": {
                    "type": "boolean",
                },
                "quantity": {
                    "type": "string",
                },
                "unit": {
                    "type": "string",
                },
                "contains_unit": {
                    "type": "boolean",
                },
            },
            "required": [
                "is_quantity",
                "quantity",
                "unit",
                "contains_unit",
            ],
        }

    @staticmethod
    def _boundary_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "boundaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pair_id": {
                                "type": "integer",
                            },
                            "relation": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "pair_id",
                            "relation",
                        ],
                    },
                },
            },
            "required": [
                "boundaries",
            ],
        }

    @staticmethod
    def _single_boundary_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "relation": {
                    "type": "string",
                },
            },
            "required": [
                "relation",
            ],
        }

    @staticmethod
    def _measurement_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "measurements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "measurement_id": {
                                "type": "integer",
                            },
                            "quantity": {
                                "type": "string",
                            },
                            "unit": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "measurement_id",
                            "quantity",
                            "unit",
                        ],
                    },
                },
            },
            "required": [
                "measurements",
            ],
        }

    @staticmethod
    def _single_measurement_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "quantity": {
                    "type": "string",
                },
                "unit": {
                    "type": "string",
                },
            },
            "required": [
                "quantity",
                "unit",
            ],
        }

    @staticmethod
    def _unit_inference_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "units": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_index": {
                                "type": "integer",
                            },
                            "unit": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "product_index",
                            "unit",
                        ],
                    },
                },
            },
            "required": [
                "units",
            ],
        }

    @staticmethod
    def _single_unit_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit": {
                    "type": "string",
                },
            },
            "required": [
                "unit",
            ],
        }

    # =========================================================================
    # QWEN JSON CALL
    # =========================================================================

    def _call_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict[str, Any],
        max_tokens: int = 700,
    ) -> Dict[str, Any]:
        response = self.llm.create_chat_completion(
            messages=messages,
            response_format={
                "type": "json_object",
                "schema": schema,
            },
            temperature=0.0,
            max_tokens=max_tokens,
        )

        content = (
            response
            .get(
                "choices",
                [{}],
            )[0]
            .get(
                "message",
                {},
            )
            .get(
                "content",
                "",
            )
        )

        content = str(
            content or ""
        ).strip()

        if not content:
            raise RuntimeError(
                "Qwen returned an empty response"
            )

        result = json.loads(
            content
        )

        if not isinstance(
            result,
            dict,
        ):
            raise RuntimeError(
                "Qwen JSON response was not an object"
            )

        return result

    # =========================================================================
    # TOKEN ROLE CLASSIFICATION
    # =========================================================================

    def _run_token_role_pass(
        self,
        prompt: str,
        transcript: str,
        tokens: Sequence[str],
    ) -> Dict[int, str]:
        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL TRANSCRIPT:\n"
                        f"{transcript}\n\n"
                        "TOKENS:\n"
                        f"{self._tokens_for_prompt(tokens)}\n\n"
                        "Return one role for EVERY token index.\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._token_roles_schema(),
            max_tokens=max(
                450,
                len(tokens) * 45,
            ),
        )

        valid_roles = {
            "number",
            "unit",
            "word",
            "separator",
        }

        role_map: Dict[int, str] = {}

        raw_tokens = result.get(
            "tokens",
            [],
        )

        if not isinstance(
            raw_tokens,
            list,
        ):
            return role_map

        for row in raw_tokens:
            if not isinstance(
                row,
                dict,
            ):
                continue

            index = row.get(
                "index"
            )

            role = str(
                row.get(
                    "role",
                    "",
                )
            ).strip().lower()

            if (
                isinstance(index, bool)
                or
                not isinstance(index, int)
                or
                not (
                    0
                    <= index
                    < len(tokens)
                )
                or
                role not in valid_roles
            ):
                continue

            if index not in role_map:
                role_map[
                    index
                ] = role

        return role_map

    def _resolve_disputed_token_role(
        self,
        transcript: str,
        tokens: Sequence[str],
        index: int,
        role_a: Optional[str],
        role_b: Optional[str],
    ) -> str:
        left = max(
            0,
            index - 2,
        )

        right = min(
            len(tokens),
            index + 3,
        )

        context_lines = "\n".join(
            f"{i}: {tokens[i]}"
            for i in range(
                left,
                right,
            )
        )

        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content":
                        TOKEN_TIE_BREAK_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL TRANSCRIPT:\n"
                        f"{transcript}\n\n"
                        "LOCAL TOKENS:\n"
                        f"{context_lines}\n\n"
                        f"TARGET INDEX: {index}\n"
                        f"TARGET TOKEN: {tokens[index]}\n"
                        f"FIRST CLASSIFIER: {role_a}\n"
                        f"SECOND CLASSIFIER: {role_b}\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._single_role_schema(),
            max_tokens=80,
        )

        role = str(
            result.get(
                "role",
                "",
            )
        ).strip().lower()

        if role in {
            "number",
            "unit",
            "word",
            "separator",
        }:
            return role

        # Coverage-first fallback:
        # never silently lose an unknown token.
        return "word"

    def _rescue_number_tokens(
        self,
        transcript: str,
        tokens: Sequence[str],
    ) -> Dict[int, Quantity]:
        """
        Independent semantic number check.

        This is intentionally separate from the four-way token-role classifier.
        A small model can confuse an unfamiliar Tamil/ASR number form with a
        word or unit. Here it only has to answer: which tokens are quantities?
        """

        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content":
                        NUMBER_RESCUE_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL TRANSCRIPT:\n"
                        f"{transcript}\n\n"
                        "TOKENS:\n"
                        f"{self._tokens_for_prompt(tokens)}\n\n"
                        "Return only tokens that are numeric quantities.\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._number_rescue_schema(),
            max_tokens=max(
                300,
                len(tokens) * 45,
            ),
        )

        rescued: Dict[
            int,
            Quantity,
        ] = {}

        raw = result.get(
            "numbers",
            [],
        )

        if not isinstance(
            raw,
            list,
        ):
            return rescued

        for row in raw:
            if not isinstance(
                row,
                dict,
            ):
                continue

            index = row.get(
                "index"
            )

            if (
                isinstance(index, bool)
                or
                not isinstance(index, int)
                or
                not (
                    0
                    <= index
                    < len(tokens)
                )
            ):
                continue

            quantity = (
                self._parse_quantity(
                    row.get(
                        "quantity"
                    )
                )
            )

            if quantity is None:
                continue

            rescued[
                index
            ] = quantity

        return rescued

    def _probe_numeric_token(
        self,
        transcript: str,
        tokens: Sequence[str],
        index: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate one suspicious token as a quantity/fraction. This also handles
        ASR tokens that accidentally contain quantity + unit together.
        """

        left = max(
            0,
            index - 2,
        )
        right = min(
            len(tokens),
            index + 3,
        )

        context_lines = "\n".join(
            f"{i}: {tokens[i]}"
            for i in range(
                left,
                right,
            )
        )

        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content":
                        SINGLE_NUMERIC_TOKEN_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL TRANSCRIPT:\n"
                        f"{transcript}\n\n"
                        "LOCAL TOKENS:\n"
                        f"{context_lines}\n\n"
                        f"TARGET INDEX: {index}\n"
                        f"TARGET TOKEN: {tokens[index]}\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._single_numeric_token_schema(),
            max_tokens=140,
        )

        if result.get(
            "is_quantity"
        ) is not True:
            return None

        quantity = (
            self._parse_quantity(
                result.get(
                    "quantity"
                )
            )
        )

        if quantity is None:
            return None

        contains_unit = bool(
            result.get(
                "contains_unit",
                False,
            )
        )

        unit = (
            self._normalize_unit(
                result.get(
                    "unit",
                    "unknown",
                )
            )
        )

        if (
            contains_unit
            and
            unit == "unknown"
        ):
            return None

        if not contains_unit:
            unit = "unknown"

        return {
            "quantity":
                quantity,
            "unit":
                unit,
            "contains_unit":
                contains_unit,
        }

    def _classify_token_roles(
        self,
        transcript: str,
        tokens: Sequence[str],
    ) -> Tuple[
        Dict[int, str],
        Dict[int, Dict[str, Any]],
    ]:
        try:
            role_a = self._run_token_role_pass(
                TOKEN_ROLE_PROMPT_A,
                transcript,
                tokens,
            )
        except Exception as error:
            print(
                "Token role pass A failed:",
                error,
                flush=True,
            )
            role_a = {}

        try:
            role_b = self._run_token_role_pass(
                TOKEN_ROLE_PROMPT_B,
                transcript,
                tokens,
            )
        except Exception as error:
            print(
                "Token role pass B failed:",
                error,
                flush=True,
            )
            role_b = {}

        print(
            "TOKEN ROLE PASS A:",
            role_a,
            flush=True,
        )
        print(
            "TOKEN ROLE PASS B:",
            role_b,
            flush=True,
        )

        final_roles: Dict[int, str] = {}
        consensus_locked: Dict[int, str] = {}

        # First preserve agreement between the two independent classifiers.
        # Agreement on NUMBER/UNIT is LOCKED: a later Qwen rescue is not
        # allowed to flip it to another semantic class.
        for index in range(len(tokens)):
            a = role_a.get(index)
            b = role_b.get(index)

            if a is not None and a == b:
                final_roles[index] = a
                if a in {"number", "unit"}:
                    consensus_locked[index] = a
                continue

            if a is not None and b is None:
                final_roles[index] = a
                continue

            if b is not None and a is None:
                final_roles[index] = b
                continue

            if a is None and b is None:
                final_roles[index] = "word"
                continue

            try:
                final_roles[index] = self._resolve_disputed_token_role(
                    transcript=transcript,
                    tokens=tokens,
                    index=index,
                    role_a=a,
                    role_b=b,
                )
            except Exception as error:
                print(
                    "Token role tie-break failed "
                    f"for index {index}:",
                    error,
                    flush=True,
                )
                final_roles[index] = "word"

        numeric_hints: Dict[int, Dict[str, Any]] = {}
        deterministic_indexes = set()

        # ------------------------------------------------------------------
        # Deterministic pass.  Measurement words always win over LLM guesses.
        # Plain Tamil/English numbers are converted mathematically here.
        # ------------------------------------------------------------------
        for index, token in enumerate(tokens):
            merged = _parse_merged_measurement_token(token)
            if merged is not None:
                quantity, unit = merged
                final_roles[index] = "number"
                numeric_hints[index] = {
                    "quantity": quantity,
                    "unit": unit,
                    "contains_unit": True,
                }
                deterministic_indexes.add(index)
                continue

            spec = _unit_spec(token)
            if spec is not None:
                final_roles[index] = "unit"
                numeric_hints.pop(index, None)
                deterministic_indexes.add(index)
                continue

            quantity = _parse_deterministic_quantity_text(token)
            if quantity is None:
                continue

            # Fractions such as கால்/அரை are context-sensitive.  Promote them
            # only beside an explicit unit, or when a classifier already saw a
            # number.  This prevents an ordinary lexical use from being stolen.
            is_fraction = float(quantity) != int(float(quantity))
            neighbor_has_unit = False
            if index > 0 and _unit_spec(tokens[index - 1]) is not None:
                neighbor_has_unit = True
            if (
                index + 1 < len(tokens)
                and _unit_spec(tokens[index + 1]) is not None
            ):
                neighbor_has_unit = True

            if (
                is_fraction
                and not neighbor_has_unit
                and role_a.get(index) != "number"
                and role_b.get(index) != "number"
            ):
                continue

            final_roles[index] = "number"
            numeric_hints[index] = {
                "quantity": quantity,
                "unit": "unknown",
                "contains_unit": False,
            }
            deterministic_indexes.add(index)

        # If a unit is known deterministically, inspect the immediate neighbor
        # for a damaged fraction such as "கா் கிலோ".
        for index, token in enumerate(tokens):
            if _unit_spec(token) is None:
                continue

            for neighbor in (index - 1, index + 1):
                if not (0 <= neighbor < len(tokens)):
                    continue
                if neighbor in deterministic_indexes:
                    continue

                quantity = _parse_deterministic_quantity_text(tokens[neighbor])
                if quantity is None:
                    continue

                final_roles[neighbor] = "number"
                numeric_hints[neighbor] = {
                    "quantity": quantity,
                    "unit": "unknown",
                    "contains_unit": False,
                }
                deterministic_indexes.add(neighbor)

        # ------------------------------------------------------------------
        # Qwen rescue is now ROLE-ONLY.  Its guessed numeric value is NOT
        # trusted.  It may promote an uncertain token to NUMBER, but it cannot
        # overwrite deterministic facts or consensus NUMBER/UNIT locks.
        # ------------------------------------------------------------------
        rescue_indexes = set()
        try:
            rescued_numbers = self._rescue_number_tokens(
                transcript=transcript,
                tokens=tokens,
            )
            rescue_indexes.update(rescued_numbers.keys())
        except Exception as error:
            print(
                "Batch number rescue failed:",
                error,
                flush=True,
            )

        for index in sorted(rescue_indexes):
            if index in deterministic_indexes:
                continue
            if consensus_locked.get(index) in {"number", "unit"}:
                continue
            if _unit_spec(tokens[index]) is not None:
                continue
            final_roles[index] = "number"

        # Focus only on unresolved disagreements / words beside a known unit.
        suspicious_indexes = set()
        for index in range(len(tokens)):
            if index in deterministic_indexes:
                continue
            if consensus_locked.get(index) in {"number", "unit"}:
                continue

            a = role_a.get(index)
            b = role_b.get(index)
            if a != b or a is None or b is None:
                suspicious_indexes.add(index)

        for index in range(len(tokens)):
            if _unit_spec(tokens[index]) is None:
                continue
            for neighbor in (index - 1, index + 1):
                if 0 <= neighbor < len(tokens):
                    if neighbor not in deterministic_indexes:
                        suspicious_indexes.add(neighbor)

        focused_role_rescue = []
        for index in sorted(suspicious_indexes):
            if _unit_spec(tokens[index]) is not None:
                continue
            try:
                hint = self._probe_numeric_token(
                    transcript=transcript,
                    tokens=tokens,
                    index=index,
                )
            except Exception as error:
                print(
                    "Focused numeric probe failed "
                    f"for index {index} ({tokens[index]}):",
                    error,
                    flush=True,
                )
                continue

            if hint is None:
                continue

            # Again: use Qwen only to decide that this is a quantity.  Do not
            # trust its arithmetic value unless our deterministic parser can
            # independently validate the token.
            final_roles[index] = "number"
            focused_role_rescue.append(index)

            deterministic_quantity = _parse_deterministic_quantity_text(
                tokens[index]
            )
            if deterministic_quantity is not None:
                numeric_hints[index] = {
                    "quantity": deterministic_quantity,
                    "unit": "unknown",
                    "contains_unit": False,
                }

        print(
            "DETERMINISTIC NUMBER HINTS:",
            numeric_hints,
            flush=True,
        )
        print(
            "NUMBER ROLE RESCUE:",
            sorted(rescue_indexes),
            flush=True,
        )
        if focused_role_rescue:
            print(
                "FOCUSED NUMBER ROLE RESCUE:",
                focused_role_rescue,
                flush=True,
            )

        return final_roles, numeric_hints

    # =========================================================================
    # PRODUCT BOUNDARIES
    # =========================================================================

    @staticmethod
    def _candidate_word_pairs(
        tokens: Sequence[str],
        roles: Dict[int, str],
    ) -> List[Dict[str, Any]]:
        pairs: List[
            Dict[str, Any]
        ] = []

        pair_id = 0

        for index in range(
            len(tokens) - 1
        ):
            if (
                roles.get(index)
                == "word"
                and
                roles.get(index + 1)
                == "word"
            ):
                pairs.append(
                    {
                        "pair_id":
                            pair_id,

                        "left_index":
                            index,

                        "right_index":
                            index + 1,

                        "left_word":
                            tokens[index],

                        "right_word":
                            tokens[index + 1],
                    }
                )

                pair_id += 1

        return pairs

    def _run_boundary_pass(
        self,
        prompt: str,
        transcript: str,
        pairs: Sequence[
            Dict[str, Any]
        ],
    ) -> Dict[int, str]:
        if not pairs:
            return {}

        pair_lines = "\n".join(
            (
                f"pair_id={pair['pair_id']} | "
                f"{pair['left_index']}:{pair['left_word']} | "
                f"{pair['right_index']}:{pair['right_word']}"
            )
            for pair in pairs
        )

        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL TRANSCRIPT:\n"
                        f"{transcript}\n\n"
                        "ADJACENT WORD PAIRS:\n"
                        f"{pair_lines}\n\n"
                        "Return every pair_id.\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._boundary_schema(),
            max_tokens=max(
                300,
                len(pairs) * 45,
            ),
        )

        final: Dict[
            int,
            str,
        ] = {}

        raw = result.get(
            "boundaries",
            [],
        )

        if not isinstance(
            raw,
            list,
        ):
            return final

        valid_pair_ids = {
            int(
                pair[
                    "pair_id"
                ]
            )
            for pair in pairs
        }

        for row in raw:
            if not isinstance(
                row,
                dict,
            ):
                continue

            pair_id = row.get(
                "pair_id"
            )

            relation = str(
                row.get(
                    "relation",
                    "",
                )
            ).strip().lower()

            if (
                isinstance(pair_id, bool)
                or
                not isinstance(
                    pair_id,
                    int,
                )
                or
                pair_id
                not in valid_pair_ids
                or
                relation
                not in {
                    "same_product",
                    "new_product",
                }
            ):
                continue

            if pair_id not in final:
                final[
                    pair_id
                ] = relation

        return final

    def _verify_same_product_pair(
        self,
        transcript: str,
        pair: Dict[str, Any],
    ) -> str:

        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content":
                        BOUNDARY_FINAL_VERIFY_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL TRANSCRIPT:\n"
                        f"{transcript}\n\n"
                        "PROPOSED MERGE:\n"
                        f"LEFT INDEX: {pair['left_index']}\n"
                        f"LEFT WORD: {pair['left_word']}\n"
                        f"RIGHT INDEX: {pair['right_index']}\n"
                        f"RIGHT WORD: {pair['right_word']}\n\n"
                        "Decide only this boundary.\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._single_boundary_schema(),
            max_tokens=80,
        )

        relation = str(
            result.get(
                "relation",
                "",
            )
        ).strip().lower()

        if relation in {
            "same_product",
            "new_product",
        }:
            return relation

        # Safety-first for product coverage:
        # an uncertain merge must not swallow a separate product.
        return "new_product"

    def _resolve_product_boundaries(
        self,
        transcript: str,
        tokens: Sequence[str],
        roles: Dict[int, str],
    ) -> Dict[int, str]:
        pairs = (
            self._candidate_word_pairs(
                tokens,
                roles,
            )
        )

        if not pairs:
            return {}

        try:
            pass_a = (
                self._run_boundary_pass(
                    BOUNDARY_PROMPT_A,
                    transcript,
                    pairs,
                )
            )
        except Exception as error:
            print(
                "Boundary pass A failed:",
                error,
                flush=True,
            )
            pass_a = {}

        try:
            pass_b = (
                self._run_boundary_pass(
                    BOUNDARY_PROMPT_B,
                    transcript,
                    pairs,
                )
            )
        except Exception as error:
            print(
                "Boundary pass B failed:",
                error,
                flush=True,
            )
            pass_b = {}

        print(
            "BOUNDARY PASS A:",
            pass_a,
            flush=True,
        )
        print(
            "BOUNDARY PASS B:",
            pass_b,
            flush=True,
        )

        final: Dict[int, str] = {}

        # Batch passes are advisory. Every genuine adjacent WORD pair gets a
        # focused semantic decision, so compositional names are not rejected
        # merely because one/both batch passes were conservative.
        for pair in pairs:
            pair_id = int(
                pair[
                    "pair_id"
                ]
            )
            left_index = int(
                pair[
                    "left_index"
                ]
            )

            a = pass_a.get(
                pair_id
            )
            b = pass_b.get(
                pair_id
            )

            try:
                verified_relation = (
                    self._verify_same_product_pair(
                        transcript=transcript,
                        pair=pair,
                    )
                )

                print(
                    "BOUNDARY FINAL VERIFY:",
                    {
                        "left":
                            pair["left_word"],
                        "right":
                            pair["right_word"],
                        "pass_a":
                            a,
                        "pass_b":
                            b,
                        "relation":
                            verified_relation,
                    },
                    flush=True,
                )

                final[
                    left_index
                ] = verified_relation

            except Exception as error:
                print(
                    "Boundary final verification failed "
                    f"for {pair['left_word']} | "
                    f"{pair['right_word']}:",
                    error,
                    flush=True,
                )
                final[
                    left_index
                ] = "new_product"

        return final

    @staticmethod
    def _build_product_spans(
        tokens: Sequence[str],
        roles: Dict[int, str],
        boundaries: Dict[int, str],
    ) -> List[Span]:
        word_indexes = [
            index
            for index in range(
                len(tokens)
            )
            if roles.get(
                index
            ) == "word"
        ]

        if not word_indexes:
            return []

        spans: List[
            Span
        ] = []

        start = word_indexes[0]
        previous = word_indexes[0]

        for index in word_indexes[1:]:
            # A number/unit/separator gap always separates products.
            if index != previous + 1:
                spans.append(
                    (
                        start,
                        previous,
                    )
                )

                start = index
                previous = index
                continue

            relation = boundaries.get(
                previous,
                "new_product",
            )

            if (
                relation
                != "same_product"
            ):
                spans.append(
                    (
                        start,
                        previous,
                    )
                )

                start = index

            previous = index

        spans.append(
            (
                start,
                previous,
            )
        )

        return spans

    @staticmethod
    def _names_from_spans(
        tokens: Sequence[str],
        spans: Sequence[Span],
    ) -> List[str]:
        return [
            " ".join(
                tokens[
                    start : end + 1
                ]
            ).strip()
            for start, end in spans
            if 0 <= start <= end < len(tokens)
        ]

    # =========================================================================
    # NUMBER / UNIT SPANS
    # =========================================================================

    @staticmethod
    def _contiguous_spans_for_role(
        roles: Dict[int, str],
        token_count: int,
        wanted_role: str,
    ) -> List[Span]:
        indexes = [
            index
            for index in range(
                token_count
            )
            if roles.get(
                index
            ) == wanted_role
        ]

        if not indexes:
            return []

        spans: List[
            Span
        ] = []

        start = indexes[0]
        previous = indexes[0]

        for index in indexes[1:]:
            if index != previous + 1:
                spans.append(
                    (
                        start,
                        previous,
                    )
                )

                start = index

            previous = index

        spans.append(
            (
                start,
                previous,
            )
        )

        return spans

    @staticmethod
    def _span_text(
        tokens: Sequence[str],
        span: Optional[Span],
    ) -> str:
        if span is None:
            return ""

        start, end = span

        return " ".join(
            tokens[
                start : end + 1
            ]
        ).strip()

    @staticmethod
    def _find_adjacent_unit_span(
        quantity_span: Span,
        unit_spans: Sequence[Span],
    ) -> Optional[Span]:
        q_start, q_end = quantity_span

        # Prefer unit immediately AFTER quantity:
        #   "ஒரு லிட்டர்"
        for unit_span in unit_spans:
            u_start, _ = unit_span

            if u_start == q_end + 1:
                return unit_span

        # Support unit immediately BEFORE quantity:
        #   "பாக்கெட் ஒன்னு"
        for unit_span in unit_spans:
            _, u_end = unit_span

            if u_end + 1 == q_start:
                return unit_span

        return None

    @staticmethod
    def _associate_product_index(
        quantity_span: Span,
        unit_span: Optional[Span],
        product_spans: Sequence[Span],
    ) -> Optional[int]:
        if not product_spans:
            return None

        region_start = quantity_span[0]
        region_end = quantity_span[1]

        if unit_span is not None:
            region_start = min(
                region_start,
                unit_span[0],
            )

            region_end = max(
                region_end,
                unit_span[1],
            )

        # Normal grocery list grammar:
        # PRODUCT -> QUANTITY -> UNIT
        left_candidates = [
            (
                product_index,
                region_start
                - product_span[1],
            )
            for product_index, product_span
            in enumerate(product_spans)
            if product_span[1]
            < region_start
        ]

        if left_candidates:
            left_candidates.sort(
                key=lambda item:
                    item[1]
            )

            return left_candidates[
                0
            ][0]

        # Also support:
        # QUANTITY -> UNIT -> PRODUCT
        right_candidates = [
            (
                product_index,
                product_span[0]
                - region_end,
            )
            for product_index, product_span
            in enumerate(product_spans)
            if product_span[0]
            > region_end
        ]

        if right_candidates:
            right_candidates.sort(
                key=lambda item:
                    item[1]
            )

            return right_candidates[
                0
            ][0]

        return None

    def _build_measurement_candidates(
        self,
        tokens: Sequence[str],
        roles: Dict[int, str],
        product_spans: Sequence[Span],
        numeric_hints: Optional[
            Dict[int, Dict[str, Any]]
        ] = None,
    ) -> List[Dict[str, Any]]:
        numeric_hints = (
            numeric_hints
            or {}
        )

        quantity_spans = (
            self._contiguous_spans_for_role(
                roles,
                len(tokens),
                "number",
            )
        )
        unit_spans = (
            self._contiguous_spans_for_role(
                roles,
                len(tokens),
                "unit",
            )
        )

        candidates: List[
            Dict[str, Any]
        ] = []

        for measurement_id, quantity_span in enumerate(
            quantity_spans
        ):
            unit_span = (
                self._find_adjacent_unit_span(
                    quantity_span,
                    unit_spans,
                )
            )

            product_index = (
                self._associate_product_index(
                    quantity_span,
                    unit_span,
                    product_spans,
                )
            )

            candidate: Dict[
                str,
                Any,
            ] = {
                "measurement_id":
                    measurement_id,
                "product_index":
                    product_index,
                "quantity_span":
                    quantity_span,
                "unit_span":
                    unit_span,
                "quantity_text":
                    self._span_text(
                        tokens,
                        quantity_span,
                    ),
                "explicit_unit_text":
                    self._span_text(
                        tokens,
                        unit_span,
                    ),
            }

            q_start, q_end = (
                quantity_span
            )

            # Only a single-token quantity span can use a single-token hint
            # directly. Multi-token numbers remain one semantic phrase.
            if q_start == q_end:
                hint = (
                    numeric_hints.get(
                        q_start
                    )
                )

                if hint is not None:
                    candidate[
                        "numeric_hint_quantity"
                    ] = hint.get(
                        "quantity"
                    )
                    candidate[
                        "numeric_hint_unit"
                    ] = hint.get(
                        "unit",
                        "unknown",
                    )
                    candidate[
                        "numeric_hint_contains_unit"
                    ] = bool(
                        hint.get(
                            "contains_unit",
                            False,
                        )
                    )

            candidates.append(
                candidate
            )

        return candidates

    # =========================================================================
    # SEMANTIC MEASUREMENT PARSING
    # =========================================================================

    def _parse_one_measurement(
        self,
        quantity_text: str,
        explicit_unit_text: str,
    ) -> Tuple[
        Quantity,
        str,
    ]:
        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content":
                        SINGLE_MEASUREMENT_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"quantity_text: {quantity_text}\n"
                        "explicit_unit_text: "
                        f"{explicit_unit_text}\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._single_measurement_schema(),
            max_tokens=120,
        )

        quantity = (
            self._parse_quantity(
                result.get(
                    "quantity"
                )
            )
        )

        unit = (
            self._normalize_unit(
                result.get(
                    "unit",
                    "unknown",
                )
            )
        )

        return (
            quantity,
            unit,
        )

    def _parse_measurement_candidates(
        self,
        candidates: Sequence[
            Dict[str, Any]
        ],
    ) -> Dict[
        int,
        Dict[str, Any],
    ]:
        if not candidates:
            return {}

        batch_result: Dict[
            int,
            Dict[str, Any],
        ] = {}

        for candidate in candidates:
            measurement_id = int(
                candidate[
                    "measurement_id"
                ]
            )

            deterministic = _deterministic_measurement(
                quantity_text=str(
                    candidate.get(
                        "quantity_text",
                        "",
                    )
                ),
                explicit_unit_text=str(
                    candidate.get(
                        "explicit_unit_text",
                        "",
                    )
                ),
            )

            if deterministic is not None:
                deterministic_quantity, deterministic_unit = deterministic
                batch_result[measurement_id] = {
                    "quantity": deterministic_quantity,
                    "unit": deterministic_unit,
                }
                continue

            hint_quantity = (
                self._parse_quantity(
                    candidate.get(
                        "numeric_hint_quantity"
                    )
                )
            )

            hint_unit = (
                self._normalize_unit(
                    candidate.get(
                        "numeric_hint_unit",
                        "unknown",
                    )
                )
            )

            hint_contains_unit = bool(
                candidate.get(
                    "numeric_hint_contains_unit",
                    False,
                )
            )

            explicit_unit_text = str(
                candidate.get(
                    "explicit_unit_text",
                    "",
                )
            ).strip()

            # ASR merged quantity+unit into one token.
            if (
                hint_quantity is not None
                and
                hint_contains_unit
                and
                hint_unit != "unknown"
            ):
                batch_result[
                    measurement_id
                ] = {
                    "quantity":
                        hint_quantity,
                    "unit":
                        hint_unit,
                }
                continue

            # Plain single-token number/fraction with no explicit unit.
            if (
                hint_quantity is not None
                and
                not explicit_unit_text
            ):
                batch_result[
                    measurement_id
                ] = {
                    "quantity":
                        hint_quantity,
                    "unit":
                        "unknown",
                }

        def quantity_text_for_parse(
            candidate: Dict[str, Any],
        ) -> str:
            explicit_unit_text = str(
                candidate.get(
                    "explicit_unit_text",
                    "",
                )
            ).strip()

            hint_quantity = (
                self._parse_quantity(
                    candidate.get(
                        "numeric_hint_quantity"
                    )
                )
            )

            hint_contains_unit = bool(
                candidate.get(
                    "numeric_hint_contains_unit",
                    False,
                )
            )

            # If the damaged ASR fraction has already been understood, do not
            # ask the model to decipher it again. Feed the mathematical fraction
            # plus the separately spoken unit to the normal converter.
            if (
                explicit_unit_text
                and
                hint_quantity is not None
                and
                not hint_contains_unit
            ):
                return str(
                    hint_quantity
                )

            return str(
                candidate.get(
                    "quantity_text",
                    "",
                )
            )

        remaining = [
            candidate
            for candidate in candidates
            if int(
                candidate[
                    "measurement_id"
                ]
            )
            not in batch_result
        ]

        if remaining:
            rows = "\n".join(
                (
                    f"{candidate['measurement_id']}: "
                    "quantity_text="
                    f"{quantity_text_for_parse(candidate)!r}; "
                    "explicit_unit_text="
                    f"{candidate['explicit_unit_text']!r}"
                )
                for candidate in remaining
            )

            remaining_ids = {
                int(
                    candidate[
                        "measurement_id"
                    ]
                )
                for candidate in remaining
            }

            try:
                result = self._call_json(
                    messages=[
                        {
                            "role": "system",
                            "content":
                                MEASUREMENT_PARSE_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": (
                                "MEASUREMENTS:\n"
                                f"{rows}\n"
                                "/no_think"
                            ),
                        },
                    ],
                    schema=self._measurement_schema(),
                    max_tokens=max(
                        350,
                        len(remaining)
                        * 90,
                    ),
                )

                raw = result.get(
                    "measurements",
                    [],
                )

                if isinstance(
                    raw,
                    list,
                ):
                    for row in raw:
                        if not isinstance(
                            row,
                            dict,
                        ):
                            continue

                        measurement_id = (
                            row.get(
                                "measurement_id"
                            )
                        )

                        if (
                            isinstance(
                                measurement_id,
                                bool,
                            )
                            or
                            not isinstance(
                                measurement_id,
                                int,
                            )
                            or
                            measurement_id
                            not in remaining_ids
                        ):
                            continue

                        quantity = (
                            self._parse_quantity(
                                row.get(
                                    "quantity"
                                )
                            )
                        )
                        unit = (
                            self._normalize_unit(
                                row.get(
                                    "unit",
                                    "unknown",
                                )
                            )
                        )

                        if quantity is None:
                            continue

                        batch_result[
                            measurement_id
                        ] = {
                            "quantity":
                                quantity,
                            "unit":
                                unit,
                        }

            except Exception as error:
                print(
                    "Batch measurement parse failed:",
                    error,
                    flush=True,
                )

        # Focused retry for anything still unresolved.
        for candidate in candidates:
            measurement_id = int(
                candidate[
                    "measurement_id"
                ]
            )

            if measurement_id in batch_result:
                continue

            try:
                quantity, unit = (
                    self._parse_one_measurement(
                        quantity_text=
                            quantity_text_for_parse(
                                candidate
                            ),
                        explicit_unit_text=str(
                            candidate[
                                "explicit_unit_text"
                            ]
                        ),
                    )
                )

                if quantity is not None:
                    batch_result[
                        measurement_id
                    ] = {
                        "quantity":
                            quantity,
                        "unit":
                            unit,
                    }

            except Exception as error:
                print(
                    "Focused measurement parse "
                    f"failed for {candidate['quantity_text']}:",
                    error,
                    flush=True,
                )

        return batch_result

    # =========================================================================
    # UNIT INFERENCE
    # =========================================================================

    def _infer_one_unit(
        self,
        product_name: str,
        quantity: Quantity,
    ) -> str:
        result = self._call_json(
            messages=[
                {
                    "role": "system",
                    "content":
                        SINGLE_UNIT_INFERENCE_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"product_name: {product_name}\n"
                        f"quantity: {quantity}\n"
                        "/no_think"
                    ),
                },
            ],
            schema=self._single_unit_schema(),
            max_tokens=80,
        )

        return self._normalize_unit(
            result.get(
                "unit",
                "unknown",
            )
        )

    def _infer_missing_units(
        self,
        products: Sequence[str],
        rows: Sequence[
            Dict[str, Any]
        ],
    ) -> Dict[int, str]:
        """
        rows contain:
            product_index
            quantity
        only for measurements with NO explicit normalized unit.
        """

        if not rows:
            return {}

        prompt_rows = "\n".join(
            (
                f"product_index={row['product_index']} | "
                f"product_name={products[row['product_index']]} | "
                f"quantity={row['quantity']}"
            )
            for row in rows
            if (
                isinstance(
                    row.get(
                        "product_index"
                    ),
                    int,
                )
                and
                0
                <= int(
                    row[
                        "product_index"
                    ]
                )
                < len(products)
            )
        )

        inferred: Dict[
            int,
            str,
        ] = {}

        try:
            result = self._call_json(
                messages=[
                    {
                        "role": "system",
                        "content":
                            UNIT_INFERENCE_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            "PRODUCTS NEEDING UNIT INFERENCE:\n"
                            f"{prompt_rows}\n"
                            "/no_think"
                        ),
                    },
                ],
                schema=self._unit_inference_schema(),
                max_tokens=max(
                    250,
                    len(rows) * 55,
                ),
            )

            raw = result.get(
                "units",
                [],
            )

            if isinstance(
                raw,
                list,
            ):
                valid_indexes = {
                    int(
                        row[
                            "product_index"
                        ]
                    )
                    for row in rows
                    if isinstance(
                        row.get(
                            "product_index"
                        ),
                        int,
                    )
                }

                for item in raw:
                    if not isinstance(
                        item,
                        dict,
                    ):
                        continue

                    product_index = (
                        item.get(
                            "product_index"
                        )
                    )

                    if (
                        isinstance(
                            product_index,
                            bool,
                        )
                        or
                        not isinstance(
                            product_index,
                            int,
                        )
                        or
                        product_index
                        not in valid_indexes
                    ):
                        continue

                    inferred[
                        product_index
                    ] = (
                        self._normalize_unit(
                            item.get(
                                "unit",
                                "unknown",
                            )
                        )
                    )

        except Exception as error:
            print(
                "Batch unit inference failed:",
                error,
                flush=True,
            )

        for row in rows:
            product_index = row.get(
                "product_index"
            )

            if (
                isinstance(
                    product_index,
                    bool,
                )
                or
                not isinstance(
                    product_index,
                    int,
                )
                or
                not (
                    0
                    <= product_index
                    < len(products)
                )
                or
                product_index
                in inferred
            ):
                continue

            try:
                inferred[
                    product_index
                ] = (
                    self._infer_one_unit(
                        product_name=
                            products[
                                product_index
                            ],
                        quantity=
                            row.get(
                                "quantity"
                            ),
                    )
                )

            except Exception as error:
                print(
                    "Focused unit inference "
                    f"failed for {products[product_index]}:",
                    error,
                    flush=True,
                )

                inferred[
                    product_index
                ] = "unknown"

        return inferred

    # =========================================================================
    # FINAL ITEMS
    # =========================================================================

    @staticmethod
    def _build_item(
        spoken_name: str,
        quantity: Quantity,
        unit: str,
    ) -> Dict[str, Any]:
        spoken_name = str(
            spoken_name or ""
        ).strip()

        unit = str(
            unit or "unknown"
        ).strip().lower()

        if not unit:
            unit = "unknown"

        if (
            quantity is not None
            and
            unit != "unknown"
        ):
            return {
                "spoken_name":
                    spoken_name,

                "search_name":
                    spoken_name,

                "quantity":
                    quantity,

                "unit":
                    unit,

                "search_mode":
                    "specific_variant",
            }

        if quantity is not None:
            return {
                "spoken_name":
                    spoken_name,

                "search_name":
                    spoken_name,

                "quantity":
                    quantity,

                "unit":
                    "unknown",

                "search_mode":
                    "related_products",
            }

        return {
            "spoken_name":
                spoken_name,

            "search_name":
                spoken_name,

            "quantity":
                None,

            "unit":
                "unknown",

            "search_mode":
                "related_products",
        }

    def _build_final_items(
        self,
        products: Sequence[str],
        candidates: Sequence[
            Dict[str, Any]
        ],
        parsed_measurements: Dict[
            int,
            Dict[str, Any],
        ],
    ) -> List[Dict[str, Any]]:
        by_product: Dict[
            int,
            Dict[str, Any],
        ] = {}

        # Attach parsed quantities to products.
        for candidate in candidates:
            measurement_id = int(
                candidate[
                    "measurement_id"
                ]
            )

            product_index = candidate.get(
                "product_index"
            )

            if (
                isinstance(
                    product_index,
                    bool,
                )
                or
                not isinstance(
                    product_index,
                    int,
                )
                or
                not (
                    0
                    <= product_index
                    < len(products)
                )
            ):
                continue

            parsed = (
                parsed_measurements.get(
                    measurement_id
                )
            )

            if parsed is None:
                continue

            quantity = parsed.get(
                "quantity"
            )

            unit = str(
                parsed.get(
                    "unit",
                    "unknown",
                )
            )

            # One normal grocery list quantity belongs to one product.
            # Keep the first valid measurement rather than letting a later
            # model row overwrite it.
            if product_index not in by_product:
                by_product[
                    product_index
                ] = {
                    "quantity":
                        quantity,

                    "unit":
                        unit,

                    "explicit_unit":
                        bool(
                            candidate.get(
                                "explicit_unit_text"
                            )
                        ),
                }

        # Infer natural units ONLY where:
        # - a quantity exists
        # - customer did not explicitly say a unit
        # - parsed unit is still unknown
        need_unit_inference: List[
            Dict[str, Any]
        ] = []

        for product_index, measurement in by_product.items():
            if (
                measurement.get(
                    "quantity"
                )
                is None
            ):
                continue

            if measurement.get(
                "explicit_unit"
            ):
                continue

            if (
                str(
                    measurement.get(
                        "unit",
                        "unknown",
                    )
                )
                != "unknown"
            ):
                continue

            need_unit_inference.append(
                {
                    "product_index":
                        product_index,

                    "quantity":
                        measurement.get(
                            "quantity"
                        ),
                }
            )

        inferred_units = (
            self._infer_missing_units(
                products,
                need_unit_inference,
            )
        )

        for product_index, inferred_unit in inferred_units.items():
            if product_index in by_product:
                by_product[
                    product_index
                ][
                    "unit"
                ] = inferred_unit

        final_items: List[
            Dict[str, Any]
        ] = []

        for product_index, product_name in enumerate(
            products
        ):
            measurement = (
                by_product.get(
                    product_index
                )
            )

            if measurement is None:
                final_items.append(
                    self._build_item(
                        spoken_name=
                            product_name,
                        quantity=None,
                        unit="unknown",
                    )
                )

                continue

            final_items.append(
                self._build_item(
                    spoken_name=
                        product_name,

                    quantity=
                        measurement.get(
                            "quantity"
                        ),

                    unit=str(
                        measurement.get(
                            "unit",
                            "unknown",
                        )
                    ),
                )
            )

        return final_items

    # =========================================================================
    # MAIN PARSER
    # =========================================================================

    def parse(
        self,
        transcript: str,
    ) -> Dict[str, Any]:
        transcript = (
            self._normalize_text(
                transcript
            )
        )

        if not transcript:
            return {
                "items": [],
            }

        tokens = (
            self._tokenize(
                transcript
            )
        )

        if not tokens:
            return {
                "items": [],
            }

        print(
            "PARSER TOKENS:",
            tokens,
            flush=True,
        )

        # ---------------------------------------------------------------------
        # 1. Classify only token semantics.
        # ---------------------------------------------------------------------

        (
            roles,
            numeric_hints,
        ) = (
            self._classify_token_roles(
                transcript,
                tokens,
            )
        )

        print(
            "FINAL TOKEN ROLES:",
            [
                (
                    index,
                    tokens[index],
                    roles.get(
                        index,
                        "word",
                    ),
                )
                for index
                in range(
                    len(tokens)
                )
            ],
            flush=True,
        )

        # ---------------------------------------------------------------------
        # 2. Resolve only product-word boundaries.
        # ---------------------------------------------------------------------

        boundaries = (
            self._resolve_product_boundaries(
                transcript,
                tokens,
                roles,
            )
        )

        print(
            "FINAL PRODUCT BOUNDARIES:",
            boundaries,
            flush=True,
        )

        product_spans = (
            self._build_product_spans(
                tokens,
                roles,
                boundaries,
            )
        )

        products = (
            self._names_from_spans(
                tokens,
                product_spans,
            )
        )

        print(
            "FINAL PRODUCT SPANS:",
            product_spans,
            flush=True,
        )

        print(
            "FINAL PRODUCTS:",
            products,
            flush=True,
        )

        if not products:
            return {
                "items": [],
            }

        # ---------------------------------------------------------------------
        # 3. Build quantity/unit regions and attach each to nearest product.
        # ---------------------------------------------------------------------

        candidates = (
            self._build_measurement_candidates(
                tokens,
                roles,
                product_spans,
                numeric_hints,
            )
        )

        print(
            "MEASUREMENT CANDIDATES:",
            candidates,
            flush=True,
        )

        # ---------------------------------------------------------------------
        # 4. Convert Tamil/Tanglish/English/ASR number phrases semantically.
        # ---------------------------------------------------------------------

        parsed_measurements = (
            self._parse_measurement_candidates(
                candidates
            )
        )

        print(
            "PARSED MEASUREMENTS:",
            parsed_measurements,
            flush=True,
        )

        # ---------------------------------------------------------------------
        # 5. Explicit units already normalized above.
        #    Missing units are inferred from product semantics here.
        # ---------------------------------------------------------------------

        final_items = (
            self._build_final_items(
                products,
                candidates,
                parsed_measurements,
            )
        )

        print(
            "FINAL PARSED ITEMS:",
            final_items,
            flush=True,
        )

        return {
            "items":
                final_items,
        }


# Single global instance used by FastAPI:
# from grocery_parser import grocery_parser
grocery_parser = GroceryParser()
