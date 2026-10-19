/*
 * Frip'Lux - lecture d'un QR code dans une PHOTO (appareil photo du téléphone).
 *
 * Une photo de téléphone est grande (ex. 4032 x 3024) et l'étiquette n'en occupe
 * souvent qu'une petite partie, parfois de travers, floue ou photographiée sur un écran.
 * On essaie donc plusieurs lectures, de la plus rapide à la plus poussée :
 *   1. l'image entière à plusieurs tailles ;
 *   2. le centre de l'image agrandi (on vise généralement l'étiquette au centre) ;
 *   3. des morceaux qui se chevauchent (étiquette décentrée).
 * On s'arrête au premier QR trouvé.
 */
(function () {
  "use strict";

  function lire(toile, contexte, image, x, y, l, h, largeurMax, essais) {
    var echelle = Math.min(1, largeurMax / l);
    var lc = Math.max(1, Math.round(l * echelle));
    var hc = Math.max(1, Math.round(h * echelle));
    toile.width = lc;
    toile.height = hc;
    contexte.imageSmoothingEnabled = true;
    contexte.imageSmoothingQuality = "high";
    contexte.drawImage(image, x, y, l, h, 0, 0, lc, hc);
    var donnees = contexte.getImageData(0, 0, lc, hc);
    var resultat = jsQR(donnees.data, lc, hc, { inversionAttempts: essais });
    return resultat && resultat.data ? resultat.data : null;
  }

  function tentatives(L, H) {
    var liste = [];
    // 1. Image entière
    [1200, 1800, 800].forEach(function (t) { liste.push([0, 0, L, H, t, "dontInvert"]); });
    // 2. Centre (60 % puis 40 % de l'image)
    [0.6, 0.4].forEach(function (f) {
      var l = L * f, h = H * f;
      liste.push([(L - l) / 2, (H - h) / 2, l, h, 1400, "dontInvert"]);
    });
    // 3. Neuf morceaux de 50 % qui se chevauchent
    [0, 0.25, 0.5].forEach(function (fy) {
      [0, 0.25, 0.5].forEach(function (fx) {
        liste.push([L * fx, H * fy, L * 0.5, H * 0.5, 1200, "dontInvert"]);
      });
    });
    // 4. Dernier essai sur l'image entière, en testant aussi les couleurs inversées
    liste.push([0, 0, L, H, 1400, "attemptBoth"]);
    return liste;
  }

  /**
   * Retourne le texte du QR code trouvé dans l'image, ou null.
   * image : élément <img> déjà chargé ; toile : élément <canvas> de travail.
   */
  function lirePhoto(image, toile) {
    var contexte = toile.getContext("2d", { willReadFrequently: true });
    var L = image.naturalWidth || image.width;
    var H = image.naturalHeight || image.height;
    var liste = tentatives(L, H);
    for (var i = 0; i < liste.length; i++) {
      var t = liste[i];
      var code = lire(toile, contexte, image, t[0], t[1], t[2], t[3], t[4], t[5]);
      if (code) return code;
    }
    return null;
  }

  window.FripluxQR = { lirePhoto: lirePhoto };
})();
