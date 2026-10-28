Шрифты приложения (самохостинг, без запросов к чужим серверам).

Inter (Regular, Medium, SemiBold) и Lora (переменный, 400-700) — свободные шрифты под лицензией SIL OFL 1.1.
Файлы урезаны (subset) до латиницы, кириллицы и нужных знаков (₽, №, −, кавычки-ёлочки), поэтому весят по ~25-47 КБ.
Тексты лицензий лежат рядом: Inter-OFL.txt, Lora-OFL.txt.

Как пересобрать (нужен fonttools): pyftsubset Inter-Regular.otf --unicodes=... --flavor=woff --output-file=Inter-Regular.woff
