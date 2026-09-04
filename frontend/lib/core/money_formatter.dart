import 'package:intl/intl.dart';

/// Converts FlowPilot's integer `_minor` amounts to display strings.
///
/// The API convention: every money field ending in `_minor` is an integer
/// (e.g. 30000000 minor CNGN == NGN 300,000.00). Never convert to a double
/// anywhere except right here, right before painting it on screen.
class MoneyFormatter {
  static String format(int minorAmount, {required String currency}) {
    final major = minorAmount / 100;
    final symbol = switch (currency.toUpperCase()) {
      'USD' => r'$',
      'EUR' => '€',
      'GBP' => '£',
      _ => '₦', // CNGN / NGN
    };
    return NumberFormat.currency(symbol: symbol, decimalDigits: 2).format(major);
  }
}
