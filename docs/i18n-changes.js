// Alerty RCB — the texts of the changelog page (zmiany.html, changelog.js) in PL / EN / UK; see docs/i18n.js.
// The change descriptions themselves are the commit subjects, in English, and stay as written.
"use strict";

i18nAdd({
  pl: {
    "chg.h1": "Historia zmian",
    "chg.lead1": "Każda wersja strony. Numer rośnie według",
    "chg.lead2": ": nowa funkcja podnosi drugą cyfrę, poprawka trzecią, zmiana łamiąca pierwszą. Listę składa automat z opisów commitów (",
    "chg.original": "Opisy zmian są w oryginale, po angielsku, tak jak w commitach.",
    "chg.group.breaking": "Zmiany łamiące",
    "chg.group.feat": "Nowe funkcje",
    "chg.group.fix": "Poprawki",
    "chg.group.perf": "Wydajność",
    "chg.group.revert": "Wycofane",
    "chg.group.other": "Inne zmiany",
    "chg.unreleased": "Jeszcze niewydane",
    "chg.bump.major": "major",
    "chg.bump.minor": "minor",
    "chg.bump.patch": "patch",
    "chg.error": "Nie udało się wczytać historii zmian: {msg}"
  },
  en: {
    "chg.h1": "Changelog",
    "chg.lead1": "Every version of the site. The number grows by",
    "chg.lead2": ": a new feature raises the second digit, a fix the third, a breaking change the first. A script builds the list from the commit messages (",
    "chg.original": "The change descriptions are the commit messages, as written.",
    "chg.group.breaking": "Breaking changes",
    "chg.group.feat": "New features",
    "chg.group.fix": "Fixes",
    "chg.group.perf": "Performance",
    "chg.group.revert": "Reverted",
    "chg.group.other": "Other changes",
    "chg.unreleased": "Not released yet",
    "chg.bump.major": "major",
    "chg.bump.minor": "minor",
    "chg.bump.patch": "patch",
    "chg.error": "Could not load the changelog: {msg}"
  },
  uk: {
    "chg.h1": "Історія змін",
    "chg.lead1": "Кожна версія сайту. Номер зростає за",
    "chg.lead2": ": нова функція збільшує другу цифру, виправлення — третю, несумісна зміна — першу. Перелік складає скрипт з описів комітів (",
    "chg.original": "Описи змін — в оригіналі, англійською, як у комітах.",
    "chg.group.breaking": "Несумісні зміни",
    "chg.group.feat": "Нові функції",
    "chg.group.fix": "Виправлення",
    "chg.group.perf": "Швидкодія",
    "chg.group.revert": "Скасовані",
    "chg.group.other": "Інші зміни",
    "chg.unreleased": "Ще не випущено",
    "chg.bump.major": "мажорна",
    "chg.bump.minor": "мінорна",
    "chg.bump.patch": "патч",
    "chg.error": "Не вдалося завантажити історію змін: {msg}"
  }
});
