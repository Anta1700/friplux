/*
 * Frip'Lux - lecture des QR codes des balles.
 * 1. Caméra en direct si le navigateur l'autorise (HTTPS ou localhost).
 * 2. Sinon (ou en plus) : photo du QR, décodée dans le téléphone.
 * 3. Saisie manuelle toujours possible.
 * Le code lu est envoyé au serveur via le formulaire (POST), qui enregistre le scan.
 */
(function () {
  "use strict";

  var formulaire = document.getElementById("form-scan");
  var champCode = document.getElementById("code");
  var toile = document.getElementById("toile");
  var contexte = toile.getContext("2d", { willReadFrequently: true });
  var envoye = false;

  function envoyer(code) {
    if (envoye) return;
    envoye = true;
    champCode.value = code.trim();
    if (navigator.vibrate) navigator.vibrate(120);
    formulaire.submit();
  }

  // Lit un QR dans une image (vidéo ou photo), redimensionnée pour aller vite.
  function decoder(source, largeurSource, hauteurSource, largeurMax, essais) {
    var echelle = Math.min(1, largeurMax / largeurSource);
    var l = Math.round(largeurSource * echelle);
    var h = Math.round(hauteurSource * echelle);
    toile.width = l;
    toile.height = h;
    contexte.drawImage(source, 0, 0, l, h);
    var image = contexte.getImageData(0, 0, l, h);
    var resultat = jsQR(image.data, l, h, { inversionAttempts: essais });
    return resultat && resultat.data ? resultat.data : null;
  }

  /* ---------- 1. Caméra en direct ---------- */
  var video = document.getElementById("video");
  var etatCamera = document.getElementById("etat-camera");
  var btnRelancer = document.getElementById("btn-relancer");
  var flux = null;

  function arreterCamera() {
    if (flux) {
      flux.getTracks().forEach(function (piste) { piste.stop(); });
      flux = null;
    }
  }

  function boucle() {
    if (!flux || envoye) return;
    if (video.readyState === video.HAVE_ENOUGH_DATA) {
      var code = decoder(video, video.videoWidth, video.videoHeight, 720, "dontInvert");
      if (code) {
        etatCamera.textContent = "QR lu : " + code;
        arreterCamera();
        envoyer(code);
        return;
      }
    }
    requestAnimationFrame(boucle);
  }

  function demarrerCamera() {
    btnRelancer.classList.add("cache");
    etatCamera.textContent = "Ouverture de la caméra…";
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false })
      .then(function (s) {
        flux = s;
        video.srcObject = s;
        return video.play();
      })
      .then(function () {
        etatCamera.textContent = "Placez le QR code dans le cadre";
        requestAnimationFrame(boucle);
      })
      .catch(function (erreur) {
        arreterCamera();
        etatCamera.textContent =
          erreur && erreur.name === "NotAllowedError"
            ? "Accès à la caméra refusé. Autorisez-le dans le navigateur, ou utilisez la photo."
            : "Caméra indisponible. Utilisez la photo ou la saisie.";
        btnRelancer.classList.remove("cache");
      });
  }

  var cameraPossible = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  if (cameraPossible) {
    document.getElementById("bloc-camera").classList.remove("cache");
    document.getElementById("btn-photo").classList.add("secondaire");
    btnRelancer.addEventListener("click", demarrerCamera);
    demarrerCamera();
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) arreterCamera();
      else if (!envoye && !flux) demarrerCamera();
    });
  } else {
    document.getElementById("info-photo").classList.remove("cache");
  }

  /* ---------- 2. Photo du QR ---------- */
  var champPhoto = document.getElementById("photo");
  var etatPhoto = document.getElementById("etat-photo");

  champPhoto.addEventListener("change", function () {
    var fichier = champPhoto.files && champPhoto.files[0];
    if (!fichier) return;
    etatPhoto.classList.remove("cache");
    etatPhoto.textContent = "Lecture de la photo…";
    var url = URL.createObjectURL(fichier);
    var image = new Image();
    image.onload = function () {
      // Plusieurs tailles : une photo nette mais lointaine se lit mieux en grand.
      var code =
        decoder(image, image.naturalWidth, image.naturalHeight, 1000, "attemptBoth") ||
        decoder(image, image.naturalWidth, image.naturalHeight, 1600, "attemptBoth") ||
        decoder(image, image.naturalWidth, image.naturalHeight, 600, "attemptBoth");
      URL.revokeObjectURL(url);
      if (code) {
        etatPhoto.textContent = "QR lu : " + code;
        envoyer(code);
      } else {
        etatPhoto.textContent =
          "QR non reconnu sur la photo. Rapprochez-vous, évitez les reflets, ou saisissez le code imprimé.";
        champPhoto.value = "";
      }
    };
    image.onerror = function () {
      etatPhoto.textContent = "Impossible d'ouvrir la photo.";
    };
    image.src = url;
  });

  /* ---------- 3. Saisie manuelle ---------- */
  formulaire.addEventListener("submit", function (evenement) {
    if (!champCode.value.trim()) {
      evenement.preventDefault();
      champCode.focus();
    }
  });
})();
