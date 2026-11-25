import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';
import 'package:myvoice_ai/features/dataset/dataset_studio_screen.dart';
import 'package:myvoice_ai/features/generate/generate_screen.dart';
import 'package:myvoice_ai/features/history/history_screen.dart';
import 'package:myvoice_ai/features/profiles/profiles_screen.dart';
import 'package:myvoice_ai/features/settings/backend_settings_screen.dart';

class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  int _selectedIndex = 0;

  static const _screens = <Widget>[
    GenerateScreen(),
    ProfilesScreen(),
    DatasetStudioScreen(),
    HistoryScreen(),
    BackendSettingsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(appStateProvider.notifier).initialize());
  }

  @override
  Widget build(BuildContext context) {
    final initialized = ref.watch(appStateProvider.select((s) => s.initialized));
    if (!initialized) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final useRail = constraints.maxWidth >= 600;
        if (useRail) {
          return Scaffold(
            body: Row(
              children: [
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: (idx) => setState(() => _selectedIndex = idx),
                  labelType: NavigationRailLabelType.all,
                  destinations: const [
                    NavigationRailDestination(
                      icon: Icon(Icons.graphic_eq_outlined),
                      selectedIcon: Icon(Icons.graphic_eq),
                      label: Text('Generate'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.record_voice_over_outlined),
                      selectedIcon: Icon(Icons.record_voice_over),
                      label: Text('Profiles'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.library_music_outlined),
                      selectedIcon: Icon(Icons.library_music),
                      label: Text('Dataset'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.history_outlined),
                      selectedIcon: Icon(Icons.history),
                      label: Text('History'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.settings_outlined),
                      selectedIcon: Icon(Icons.settings),
                      label: Text('Backend'),
                    ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(child: _screens[_selectedIndex]),
              ],
            ),
          );
        }

        return Scaffold(
          body: _screens[_selectedIndex],
          bottomNavigationBar: NavigationBar(
            selectedIndex: _selectedIndex,
            onDestinationSelected: (idx) => setState(() => _selectedIndex = idx),
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.graphic_eq_outlined),
                selectedIcon: Icon(Icons.graphic_eq),
                label: 'Generate',
              ),
              NavigationDestination(
                icon: Icon(Icons.record_voice_over_outlined),
                selectedIcon: Icon(Icons.record_voice_over),
                label: 'Profiles',
              ),
              NavigationDestination(
                icon: Icon(Icons.library_music_outlined),
                selectedIcon: Icon(Icons.library_music),
                label: 'Dataset',
              ),
              NavigationDestination(
                icon: Icon(Icons.history_outlined),
                selectedIcon: Icon(Icons.history),
                label: 'History',
              ),
              NavigationDestination(
                icon: Icon(Icons.settings_outlined),
                selectedIcon: Icon(Icons.settings),
                label: 'Backend',
              ),
            ],
          ),
        );
      },
    );
  }
}
