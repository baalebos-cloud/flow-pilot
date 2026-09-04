const Map<String, String> currencyShieldReasonCopy = {
  'PROTECTED_POCKET': 'This pocket is protected and cannot fund Currency Shield.',
  'UNSUPPORTED_PAIR': 'The demo currently supports CNGN to USD only.',
  'AMOUNT_EXCEEDS_SAFETY_LIMIT': 'Choose a smaller amount within the safety limit.',
  'ALERT_THRESHOLD_NOT_REACHED': 'Market movement has not reached the recommendation threshold.',
};

String friendlyReasons(List<String> reasons) {
  if (reasons.isEmpty) return 'This request was rejected.';
  return reasons.map((r) => currencyShieldReasonCopy[r] ?? r).join('\n');
}
