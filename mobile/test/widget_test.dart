import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myvoice_ai/app.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';
import 'package:myvoice_ai/data/services/api_client_service.dart';
import 'package:myvoice_ai/data/services/local_storage_service.dart';

class _TestAppStateNotifier extends AppStateNotifier {
  _TestAppStateNotifier()
      : super(LocalStorageService(), ApiClientService()) {
    state = const AppState(initialized: true);
  }

  @override
  Future<void> initialize() async {}
}

void main() {
  testWidgets('MyVoiceApp renders navigation tabs without crashing', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appStateProvider.overrideWith((ref) => _TestAppStateNotifier()),
        ],
        child: const MyVoiceApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('MyVoice AI Studio'), findsOneWidget);
    expect(find.text('Profiles'), findsOneWidget);
    expect(find.text('Dataset'), findsOneWidget);
    expect(find.text('History'), findsOneWidget);
    expect(find.text('Backend'), findsOneWidget);

    await tester.tap(find.text('Dataset'));
    await tester.pumpAndSettle();
    expect(find.text('Tier 2: Dataset Studio'), findsOneWidget);
  });
}
