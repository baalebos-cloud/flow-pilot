import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';

import 'router.dart';

class FlowPilotApp extends StatelessWidget {
  const FlowPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      debugShowCheckedModeBanner: false,
      title: 'FlowPilot × BMONI',
      theme: BMoniTheme.darkTheme(),
      routerConfig: appRouter,
    );
  }
}
