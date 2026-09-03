import 'package:intl/intl.dart';
String formatCurrency(double value) => NumberFormat.currency(locale: 'en_NG', symbol: '₦', decimalDigits: 2).format(value);
String formatDate(DateTime value) => DateFormat('dd MMM yyyy, HH:mm').format(value);
String signedAmount(double value, bool incoming) => '${incoming ? '+' : '-'}${formatCurrency(value)}';
