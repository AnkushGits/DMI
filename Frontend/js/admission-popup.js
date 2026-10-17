(() => {

  const studentDataEndpoint =
    "https://script.google.com/macros/s/AKfycbyfd5rz1-keZdeMrHwfwn_dpFtGSdLFDaVNw1a9f-UxnN8hD1Sdl2Dn6Hohes6JN62T/exec";



  /*
   * Admission enquiries are stored only in Google Sheets
   * through a Google Apps Script web app. The "place" value is
   * sent as its own field so it lands in its own column.
   */

  async function submitStudentDetails(details) {

    if (
      !studentDataEndpoint.startsWith(
        "https://script.google.com/macros/s/"
      ) ||
      !studentDataEndpoint.endsWith("/exec")
    ) {
      throw new Error(
        "Google Apps Script Web App URL is not configured."
      );
    }

    await fetch(studentDataEndpoint, {
      method: "POST",


      mode: "no-cors",

      headers: {
        "Content-Type": "text/plain;charset=utf-8"
      },

      body: JSON.stringify(details),

      keepalive: true
    });
  }

  const markup = `
    <div
      class="dm-admission-popup-overlay"
      id="dmAdmissionPopupOverlay"
      aria-hidden="true"
    >

      <section
        class="dm-admission-popup"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dmAdmissionPopupTitle"
        aria-describedby="dmAdmissionPopupDescription"
      >

        <div class="dm-admission-popup-image">

          <img
            src="/assets/images/admission-popup.png"
            alt="DM Skills Institute student building a career with practical skills"
          >

        </div>


        <div class="dm-admission-popup-content">

          <button
            class="dm-admission-popup-close"
            type="button"
            aria-label="Close admission inquiry popup"
          >
            &times;
          </button>


          <span class="dm-admission-popup-badge">
            Admissions Open &bull; 2026
          </span>


          <h2
            class="dm-admission-popup-title"
            id="dmAdmissionPopupTitle"
          >
            DM Skills Institute
          </h2>


          <p
            class="dm-admission-popup-copy"
            id="dmAdmissionPopupDescription"
          >
            Start your career with practical computer skills.
            <br>
            &ldquo;Enquire now for course details and admission information.&rdquo;
          </p>


          <form
            class="dm-admission-popup-form"
            id="dmAdmissionPopupForm"
          >

            <div class="dm-admission-popup-field">

              <label for="dmAdmissionFullName">
                Full Name
              </label>

              <input
                id="dmAdmissionFullName"
                name="fullName"
                type="text"
                maxlength="120"
                placeholder="Enter your full name"
                autocomplete="name"
                required
              >

            </div>


            <div class="dm-admission-popup-field">

              <label for="dmAdmissionMobile">
                Mobile Number
              </label>

              <input
                id="dmAdmissionMobile"
                name="mobileNumber"
                type="tel"
                maxlength="10"
                pattern="[6-9][0-9]{9}"
                placeholder="Enter 10-digit mobile number"
                autocomplete="tel"
                required
              >

            </div>


            <div class="dm-admission-popup-field">

              <label for="dmAdmissionCourse">
                Select Course
              </label>

              <select
                id="dmAdmissionCourse"
                name="course"
                required
              >

                <option
                  value=""
                  selected
                  disabled
                >
                  Select a course
                </option>

                <option value="Tally Professional">
                  Tally Professional
                </option>

                <option value="GST Using Tally Prime">
                  GST Using Tally Prime
                </option>

                <option value="Advanced Excel">
                  Advanced Excel
                </option>

                <option value="Accounting">
                  Accounting
                </option>

                <option value="Front Office Coordinator">
                  Front Office Coordinator
                </option>

                <option value="RS-CIT">
                  RS-CIT
                </option>

              </select>

            </div>


            <div class="dm-admission-popup-field">

              <label for="dmAdmissionPlace">
                Place
              </label>

              <input
                id="dmAdmissionPlace"
                name="place"
                type="text"
                maxlength="120"
                placeholder="Enter your city / town"
                autocomplete="address-level2"
              >

            </div>


            <button
              class="dm-admission-popup-submit"
              type="submit"
            >
              Submit Details
            </button>


            <p
              class="dm-admission-popup-status"
              id="dmAdmissionPopupStatus"
              role="status"
              aria-live="polite"
            ></p>

          </form>


          <section
            class="dm-admission-popup-thank-you"
            id="dmAdmissionPopupThankYou"
            aria-labelledby="dmAdmissionPopupThankYouTitle"
            hidden
          >

            <h3 id="dmAdmissionPopupThankYouTitle">
              Thank you!
            </h3>

            <p>
              Your details have been sent to our admissions team.
              We will contact you soon.
            </p>

            <button
              class="dm-admission-popup-done"
              id="dmAdmissionPopupDone"
              type="button"
            >
              Done
            </button>

          </section>

        </div>

      </section>

    </div>
  `;


  document.body.insertAdjacentHTML(
    "beforeend",
    markup
  );


  /*
   * =========================================================
   * GET ELEMENTS
   * =========================================================
   */

  const overlay =
    document.getElementById(
      "dmAdmissionPopupOverlay"
    );

  const closeButton =
    overlay.querySelector(
      ".dm-admission-popup-close"
    );

  const form =
    document.getElementById(
      "dmAdmissionPopupForm"
    );

  const formStatus =
    document.getElementById(
      "dmAdmissionPopupStatus"
    );

  const thankYou =
    document.getElementById(
      "dmAdmissionPopupThankYou"
    );

  const submitButton =
    form.querySelector(
      ".dm-admission-popup-submit"
    );

  const doneButton =
    document.getElementById(
      "dmAdmissionPopupDone"
    );


  /*
   * =========================================================
   * CLOSE POPUP
   * =========================================================
   */

  function closePopup() {

    overlay.classList.remove(
      "dm-admission-popup-visible"
    );

    overlay.setAttribute(
      "aria-hidden",
      "true"
    );
  }


  closeButton.addEventListener(
    "click",
    closePopup
  );


  doneButton.addEventListener(
    "click",
    closePopup
  );


  overlay.addEventListener(
    "click",
    (event) => {

      if (event.target === overlay) {
        closePopup();
      }

    }
  );


  document.addEventListener(
    "keydown",
    (event) => {

      if (
        event.key === "Escape" &&
        overlay.classList.contains(
          "dm-admission-popup-visible"
        )
      ) {

        closePopup();

      }

    }
  );


  /*
   * =========================================================
   * SHOW POPUP AFTER 2.3 SECONDS
   * =========================================================
   */

  window.setTimeout(() => {

    overlay.classList.add(
      "dm-admission-popup-visible"
    );

    overlay.setAttribute(
      "aria-hidden",
      "false"
    );

  }, 2300);


  /*
   * =========================================================
   * FORM SUBMISSION
   * =========================================================
   */

  form.addEventListener(
    "submit",
    async (event) => {

      event.preventDefault();


      if (!form.reportValidity()) {
        return;
      }


      const fullName =
        document
          .getElementById("dmAdmissionFullName")
          .value
          .trim();


      const mobileNumber =
        document
          .getElementById("dmAdmissionMobile")
          .value
          .trim();


      const course =
        document
          .getElementById("dmAdmissionCourse")
          .value;


      const place =
        document
          .getElementById("dmAdmissionPlace")
          .value
          .trim();


      /*
       * Data that will be sent to Google Apps Script
       */

      const studentData = {

        name: fullName,

        phone: mobileNumber,

        course: course,

        place: place,

        /*
         * The popup has no free-text box. The field is kept
         * so the popup and the admission enquiry form send
         * the exact same payload into the same sheet columns.
         */

        message: "",

        source: "Website popup",

        submittedAt:
          new Date().toISOString()

      };


      submitButton.disabled = true;

      formStatus.textContent =
        "Submitting your details...";


      try {

        await submitStudentDetails(studentData);

        /*
         * Because no-cors prevents JavaScript
         * from reading the Google response,
         * reaching this point means the request
         * was sent successfully.
         */

        form.hidden = true;

        thankYou.hidden = false;


      } catch (error) {

        console.error(
          "Google Sheet submission error:",
          error
        );


        formStatus.textContent =
          "Unable to send your details. Please try again.";


        submitButton.disabled = false;

      }

    }
  );

})();