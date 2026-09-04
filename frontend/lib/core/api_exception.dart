/// A normalized error thrown by [ApiClient] for every failed request.
///
/// [message] is always safe, human-readable copy suitable for direct
/// display in the UI. [statusCode] and [reasons] are preserved for
/// screen-specific handling (e.g. mapping 422 policy reason codes to
/// friendlier copy) and for debug logging.
class ApiException implements Exception {
  ApiException({
    required this.message,
    this.statusCode,
    this.reasons,
    this.rawDetail,
  });

  final String message;
  final int? statusCode;

  /// Structured policy/validation reason codes from a 422 response body,
  /// e.g. `["PROTECTED_POCKET"]` from the Currency Shield endpoint.
  final List<String>? reasons;

  /// The raw `detail` field from the backend, kept for debug logs only.
  final dynamic rawDetail;

  bool get isUnauthorized => statusCode == 401;
  bool get isConflict => statusCode == 409;
  bool get isValidationRejection => statusCode == 422;
  bool get isServiceUnavailable => statusCode == 503;

  @override
  String toString() => message;
}
