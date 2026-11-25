class AppConstants {
  AppConstants._();

  static const String appName = 'MyVoice AI';
  static const String defaultBackendUrl = 'http://10.0.2.2:8000';
  static const int targetDatasetMinutes = 15;
  static const int maxTextLength = 1000;

  static const List<Map<String, String>> backendPresets = [
    {
      'label': 'Android Emulator (Host PC)',
      'url': 'http://10.0.2.2:8000',
    },
    {
      'label': 'Local Wi-Fi PC Example',
      'url': 'http://192.168.1.100:8000',
    },
    {
      'label': 'Cloudflare / Colab Tunnel Example',
      'url': 'https://your-tunnel.trycloudflare.com',
    },
  ];
}
