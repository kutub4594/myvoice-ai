import 'package:myvoice_ai/core/constants/app_constants.dart';
import 'package:myvoice_ai/core/errors/app_exception.dart';

class BackendConfig {
  const BackendConfig({
    this.baseUrl = AppConstants.defaultBackendUrl,
    this.apiToken = '',
    this.allowLocalHttpDev = false,
    this.requestTimeoutSeconds = 90,
  });

  static const Set<String> _localDevHosts = {
    'localhost',
    '127.0.0.1',
    '::1',
    '10.0.2.2',
  };

  final String baseUrl;
  final String apiToken;
  final bool allowLocalHttpDev;
  final int requestTimeoutSeconds;

  bool get isPlainHttp => baseUrl.trim().toLowerCase().startsWith('http://');

  bool get isExplicitLocalDevHost {
    final normalized = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(normalized);
    if (uri == null || uri.host.isEmpty) return false;
    return _localDevHosts.contains(uri.host.toLowerCase());
  }

  /// Validates URI format and enforces HTTPS for all remote backend connections.
  Uri validateAndResolveUri() {
    final normalized = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(normalized);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw const AppException('Invalid backend URL. Enter a valid https:// address.');
    }
    final scheme = uri.scheme.toLowerCase();
    if (scheme == 'https') {
      return uri;
    }
    if (scheme == 'http') {
      if (allowLocalHttpDev && isExplicitLocalDevHost) {
        return uri;
      }
      throw const AppException(
        'HTTPS is required for remote backends. Plain HTTP is allowed only for '
        'localhost, 127.0.0.1, ::1, or 10.0.2.2 when Local HTTP Dev mode is enabled.',
      );
    }
    throw const AppException('Unsupported URL scheme. Use https://.');
  }

  BackendConfig copyWith({
    String? baseUrl,
    String? apiToken,
    bool? allowLocalHttpDev,
    int? requestTimeoutSeconds,
  }) {
    return BackendConfig(
      baseUrl: baseUrl ?? this.baseUrl,
      apiToken: apiToken ?? this.apiToken,
      allowLocalHttpDev: allowLocalHttpDev ?? this.allowLocalHttpDev,
      requestTimeoutSeconds: requestTimeoutSeconds ?? this.requestTimeoutSeconds,
    );
  }
}
