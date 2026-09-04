import 'package:flutter/material.dart';

import 'router.dart';
import 'theme/app_theme.dart';

class FlowPilotApp extends StatelessWidget {
  const FlowPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      debugShowCheckedModeBanner: false,
      title: 'FlowPilot × BMONI',
      theme: buildAppTheme(),
      routerConfig: appRouter,
    );
  }
}