import 'package:dio/dio.dart';

import 'api_exception.dart';
import 'environment.dart';
import 'secure_token_store.dart';

/// The single owner of the base URL, headers, bearer-token injection,
/// timeouts, and response/error decoding. Repositories call this — widgets
/// never build raw HTTP requests themselves.
class ApiClient {
  ApiClient({SecureTokenStore? tokenStore})
      : _tokenStore = tokenStore ?? SecureTokenStore() {
    _dio = Dio(
      BaseOptions(
        baseUrl: Environment.baseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 20),
        headers: {'Content-Type': 'application/json'},
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _tokenStore.read();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  late final Dio _dio;
  final SecureTokenStore _tokenStore;

  Future<dynamic> get(String path) async {
    try {
      final response = await _dio.get(path);
      return response.data;
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  Future<dynamic> post(
    String path, {
    Map<String, dynamic>? data,
    Map<String, String>? headers,
  }) async {
    try {
      final response = await _dio.post(
        path,
        data: data,
        options: headers != null ? Options(headers: headers) : null,
      );
      return response.data;
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  ApiException _mapError(DioException e) {
    final status = e.response?.statusCode;
    final body = e.response?.data;
    final detail = body is Map ? body['detail'] : null;

    // 422 rejections sometimes arrive as {"detail": {"status": ..., "reasons": [...]}}
    List<String>? reasons;
    String? detailText;
    if (detail is Map && detail['reasons'] is List) {
      reasons = (detail['reasons'] as List).map((e) => e.toString()).toList();
    } else if (detail is String) {
      detailText = detail;
    }

    final message = switch (status) {
      401 => 'Your session has expired. Please log in again.',
      403 => 'Account setup is incomplete. Please try again shortly.',
      409 => detailText ?? 'This action conflicts with the current state.',
      422 => detailText ?? 'This request was rejected. Please review the details.',
      503 => 'The service is temporarily unavailable. Please try again.',
      _ => (e.type == DioExceptionType.connectionTimeout ||
              e.type == DioExceptionType.receiveTimeout ||
              e.type == DioExceptionType.sendTimeout)
          ? 'The request timed out. Check your connection and try again.'
          : (e.type == DioExceptionType.connectionError)
              ? 'Could not reach the server. Check your connection and the backend is running.'
              : 'Something went wrong. Please try again.',
    };

    return ApiException(
      message: message,
      statusCode: status,
      reasons: reasons,
      rawDetail: detail,
    );
  }
}
