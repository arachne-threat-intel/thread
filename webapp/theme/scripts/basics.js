// NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

// The current sentence that's selected
var sentence_id = 0;
// A temporarily highlighted sentence
var tempHighlighted = undefined;
// The classes used for highlighting a sentence or image
var highlightClass = "highlight-sentence";
var highlightClassImg = "imgHighlight";
// The class used when a sentence is clicked
var clickedClass = "report-sentence-clicked";
// ID selectors for report-sentence buttons
var delSenBtn = "#delSenBtn";
var missingTechBtn = "#missingTechBtn";
const iocSwitchSelector = "#iocSwitch";
const iocSavedBoxId = "iocSavedBox";
const iocSuggestionBoxSelector = "#iocSuggestionBox";
const iocSuggestionBtnSelector = "#iocSuggestionBtn";
const iocSuggestSaveBtnSelector = "#iocSuggestSaveBtn";
const iocUpdateBtnSelector = "#iocUpdateBtn";
var senTTPForm = "#ttpDatesForm";
// The URL for the rest requests
var restUrl = $("script#basicsScript").data("rest-url");
// If this script is being run locally
var isLocal = $("script#basicsScript").data("run-local");
// Is this report completed?
var isCompleted = false;
// External-font-loading: pdfMake-config and boolean to represent if we loaded the font
var exoConfig = {
  normal: "Exo-Light.ttf",
  bold: "Exo-Bold.ttf",
  italics: "Exo-Italic.ttf",
  bolditalics: "Exo-BoldItalic.ttf"
};
var exoFontReady = false;
// HTML for icons when adding/removing list items
var addLiHTML = "<a class= 'list-delta' data-bs-toggle='tooltip' data-bs-placement='top' title='Pending: This is a new selection.'>";
addLiHTML += "<span class='fa-solid fa-circle-plus glyphicon glyphicon-plus-sign text-success'></span></a>";
var remLiHTML = "<a class= 'list-delta' data-bs-toggle='tooltip' data-bs-placement='top' title='Pending: This has been unselected.'>";
remLiHTML += "<span class='fas fa-trash-alt glyphicon glyphicon-trash text-danger'></span></a>";

function restRequest(type, data, callback=null, url=restUrl, onError=null) {
  $.ajax({
    url: url,
    type: type,
    contentType: "application/json",
    data: JSON.stringify(data),
    success: function(data, textStatus, xhr) {
      if (xhr?.responseJSON?.alert_user && xhr?.responseJSON?.info) {
        alert(xhr.responseJSON.info);
      }
      if (callback instanceof Function) {
        callback(data);
      }
    },
    error: function (xhr, ajaxOptions, thrownError) {
      if (xhr?.responseJSON?.alert_user && xhr?.responseJSON?.error) {
        alert(xhr.responseJSON.error);
      }
      if (onError instanceof Function) {
        onError();
      }
   }
  });
}

function page_refresh() {
  window.location.reload(true);
}

function prefixHttp(urlInput) {
  // Obtain the current url for this input box
  var initialInput = urlInput.value;
  var url = initialInput || "";
  url = url.trim();
  // Flag to track if we updated the url value
  var updateUrl = false;
  // If there is no url, there is nothing to add a prefix to
  if (!url) {
      return;
  }
  // Proceed to prefix with http if http(s) has not been specified
  if(!(/^https?:\/\//i.test(url))){
    url = "http://" + url;
    updateUrl = true;
  }
  // If we updated the url, update the input box
  if (updateUrl) {
    urlInput.value = url;
    // Revert to initial value if invalid
    if (!urlInput.reportValidity()) {
      urlInput.value = initialInput;
    }
  }
}

function removeSentenceFromReviewList(sentence_id, forceDelete) {
  // If all flags for a sentence have now been removed, remove the sentence from the to-review list
  var liSelector = `li#outstanding-sen-${sentence_id}`;
  if (forceDelete || !$(`${liSelector} a`).length) {
    $(liSelector).remove();
    // As we removed an li, check if this is the last one > if so, all sentences have been reviewed
    var ulSelector = "ul#outstandingTechsList";
    if (!$(`${ulSelector} li`).length) {
      $(ulSelector).remove();
      // Display the no-more-to-review message
      $("span#techsNoMoreConfNote").prop("hidden", false);
    }
  }
}

function remove_sentence() {
  // The selected image or sentence
  var selectedSentence = document.getElementById(`elmt${sentence_id}`);
  var selectedImage = document.getElementById(`img${sentence_id}`);
  // The final selected element to be removed
  var selected = undefined;
  // Data which informs user of what is being removed
  var messageInfo = "";
  // If it is a sentence that is selected
  if (selectedSentence) {
    // Scroll sentence into view - commented out due to timings with confirm() box and browser compatibility
    // selectedSentence.scrollIntoView({block: "center", inline: "center"});
    // Prepare the first three words of the sentence as a reminder to the user of the sentence that is selected
    sen_text = selectedSentence.innerText;
    truncated = sen_text.split(" ").slice(0,3).join(" ");
    // Add trailing ellipsis if the sentence has more than three words
    truncated += (truncated == sen_text) ? "" : "...";
    truncated = truncated.trim();
    // Don't display preview for sentence if too long
    messageInfo = truncated.length > 40 ? "sentence" : `sentence ("${truncated}")`;
    // Flag selected to be this sentence to be removed
    selected = selectedSentence;
  } else if (selectedImage) {  // Else if an image is selected
    // Scroll image into view - commented out due to timings with confirm() box and browser compatibility
    // selectedImage.scrollIntoView({block: "center", inline: "center"});
    messageInfo = "image";
    // Flag selected to be this image to be removed
    selected = selectedImage;
  } else {  // Else we do not have an item selected for removal
    alert("Unable to determine selected item in report. Please try refreshing page.");
    return;
  }
  // Confirm with the user that this is being removed
  if (confirm("Are you sure you want to remove the currently selected " + messageInfo
        + "? This can only be retrieved by re-submitting or rollbacking this report.")) {
    // Send off request to delete from the db
    restRequest("POST", {"index": "remove_sentence", "sentence_id": sentence_id}, function() {
      // Remove the element itself and any related elements (e.g. buffering <br>s, the to-review list)
      selected.remove();
      $(`.elmtRelated${sentence_id}`).remove();
      removeSentenceFromReviewList(sentence_id, true);
      // Nothing is currently selected after this removal
      tempHighlighted = undefined;
      // Disable further actions until another item is selected
      $(missingTechBtn).prop("disabled", true);
      $(delSenBtn).prop("disabled", true);
      $(iocSwitchSelector).prop("disabled", true);
      $(iocSuggestionBtnSelector).prop("disabled", true);
      $(iocSuggestSaveBtnSelector).prop("disabled", true);
      $(iocUpdateBtnSelector).prop("disabled", true);
      $(`#ioc-icon-${sentence_id}`).remove();
      $(senTTPForm).prop("hidden", true);
      // Reset any sentence-techniques lists
      $("#tableSentenceInfo tr").remove();
      $("#confirmedSentenceInfo tr").remove();
    });
  }
}

function acceptAttack(id, attack_uid) {
  acceptReject(id, attack_uid, true, false, false);
}

function ignoreAttack(id, attack_uid) {
  acceptReject(id, attack_uid, false, true, false);
}

function rejectAttack(id, attack_uid) {
  acceptReject(id, attack_uid, false, false, true);
}

function acceptReject(sentence_id, attack_uid, accepting=false, ignoring=false, rejecting=false) {
  // Either accepting or rejecting needs to be specified
  if ((accepting && rejecting) || !(accepting || rejecting || ignoring)) {
    throw new Error("Sentence-attack: accepting or rejecting or ignoring not specified.");
  }

  const action = accepting ? "add_attack" : ignoring ? "ignore_attack" : "reject_attack";

  restRequest("POST", {"index": action, "sentence_id": sentence_id, "attack_uid": attack_uid}, function() {
    // Update the to-review list
    $(`a#outstanding-tech-${sentence_id}-${attack_uid}`).remove();
    removeSentenceFromReviewList(sentence_id);
    // Retrieve and display the list of attacks
    sentenceContext(sentence_id);
  });
}

function deleteReport(reportTitle) {
  if (confirm("Are you sure you want to delete this report?")) {
    restRequest("POST", {"index": "delete_report", "report_title": reportTitle}, page_refresh);
  }
}

function rollbackReport(reportTitle) {
  if (confirm("Are you sure you want to rollback this report to NEEDS REVIEW?")) {
    restRequest("POST", {"index": "rollback_report", "report_title": reportTitle}, page_refresh);
  }
}

function finish_analysis(reportTitle) {
  var msg = "Are you sure you are finished with this report?";
  if (!isLocal) {
    msg += "\n\nOnce this report is finalised, it will be deleted from Thread after 24 hours.";
  }
  if (confirm(msg)) {
    restRequest("POST", {"index":"set_status", "set_status": "completed", "report_title": reportTitle}, page_refresh);
  }
}

function updateReportDates(reportTitle) {
  if(!document.getElementById("reportDatesForm").reportValidity()) {
    return;
  }
  // Send off the request with the inputted dates
  var dateOf = document.getElementById("dateOf").value;
  var startDate = document.getElementById("startDate").value;
  var endDate = document.getElementById("endDate").value;
  var sameDates = $("#dateRange").prop("checked");
  var applyToAll = $("#applyToAllDates").prop("checked");
  restRequest("POST", {"index": "update_report_dates", "report_title": reportTitle, "same_dates": sameDates,
                       "apply_to_all": applyToAll, "date_of": dateOf, "start_date": startDate, "end_date": endDate});
}

function submit(data, submitButton) {
  // Do extra checks if this is not locally run
  if(!isLocal) {
    // IDs of fields related to private-report switch
    var privateSwitchID = $(submitButton).data("private-switch-id");
    var checkboxID = $(privateSwitchID).data("paired-checkbox");
    var consentCheckboxID = $(privateSwitchID).data("paired-consent-checkbox-id");
    // Check confirmation checkbox
    if (!document.getElementById(checkboxID.replace("#", "")).reportValidity()
        || !document.getElementById(consentCheckboxID).reportValidity()) {
      return;
    }
    // Update request-data with private-report boolean
    data.private = $(privateSwitchID).is(":checked");
  }
  restRequest("POST", data, page_refresh);
}

function submit_report(submitButton) {
  // The URL and title field values comma-separated
  var url = document.getElementById("url");
  var title = document.getElementById("title");
  // Proceed with submitting if both fields are valid
  if (url.reportValidity() && title.reportValidity()) {
    submit({"index":"insert_report", "url":url.value, "title":title.value}, submitButton);
  }
}

function upload_file(uploadButton) {
  // Check the file field is valid before proceeding
  var fileField = document.getElementById("csv_file");
  if (!fileField.reportValidity()) {
    return;
  }
  // Parse the file and send in request to complete submission
  var file = fileField.files[0];
  if (file) {
    var reader = new FileReader();
    reader.readAsText(file, "UTF-8");
    reader.onload = function(evt) {
      submit({"index": "insert_csv", "file": evt.target.result}, uploadButton);
    }
    reader.onerror = function(evt) {
      alert("Error reading file; this could be because of file-permissions or the file recently being changed. "
            + "Please refresh the page and try again.");
    }
  }
}

function show_dropdown() {
  document.getElementById("myDropdown").classList.toggle("show");
}

function filterFunction(input1, id1) {
  var input, filter, ul, li, a, i;
  input = document.getElementById(input1);
  filter = input.value.toUpperCase();
  div = document.getElementById(id1);
  a = div.getElementsByTagName("button");
  for (i = 0; i < a.length; i++) {
    txtValue = a[i].textContent || a[i].innerText;
    if (txtValue.toUpperCase().indexOf(filter) > -1) {
      a[i].style.display = "";
    } else {
      a[i].style.display = "none";
    }
  }
}

function savedAlert() {
  console.log("saved");
}

 function autoHeight() {
  if ($("html").height() < $(window).height()) {
    $("footer").addClass("sticky-footer");
  } else {
    $("footer").removeClass("sticky-footer");
  }
}

function sentenceContext(data) {
  // Update selected sentence global variable
  sentence_id = data;
  // Fire off requests to get info on this sentence
  restRequest("POST", {"index":"sentence_context", "sentence_id": data}, updateSentenceContext);
  restRequest("POST", {"index":"confirmed_attacks", "sentence_id": data}, updateConfirmedContext);
}

function updateSentenceContext(responseData) {
  // If we previously highlighted a sentence before and this is a new sentence, remove the previous highlighting
  if (tempHighlighted !== undefined && tempHighlighted !== sentence_id) {
    $("#elmt" + tempHighlighted).removeClass(highlightClass);
    $("#img" + tempHighlighted).removeClass(highlightClassImg);
    tempHighlighted = undefined;
  }
  // Regardless of what is clicked, remove any previous clicked-styling for report sentences
  $(".report-sentence").removeClass(clickedClass);
  // Reset any sentence data
  $("#tableSentenceInfo tr").remove();
  $(iocSuggestionBoxSelector).val("");
  $("#" + iocSavedBoxId).val("");
  // Flag we will enable any disabled sentence buttons
  enableSenButtons = true;
  // If this sentence has attacks, display the attacks as normal
  data = responseData.techniques || [];
  iocText = responseData.ioc || "";
  if (data && data.length > 0) {
    // Highlight to the user this sentence has been clicked
    $("#elmt" + sentence_id).addClass(clickedClass);
    $.each(data, function(index, op) {
      // Is this a technique or software URL?
      const opAttack = op.attack_uid || "";
      const opAttackURL = (opAttack.startsWith("malware") || opAttack.startsWith("tool")) ? "software" : "techniques";
      // Before the attack-name, flag if deprecated/revoked
      const attackCell = "<td>" + (op.inactive ? "<b>!</b> " : "") + "<a href=https://attack.mitre.org/"
            // For the href, replace any '.' in the TID with a '/' as that is the URL format for sub-techniques
            + opAttackURL + "/" + op.attack_tid.replace(".", "/") + " target=_blank>"
            // Prefix the name with the parent-technique (if it is a sub-technique), else just print the name
            + (op.attack_parent_name ? `${op.attack_parent_name}: ${op.attack_technique_name}` : op.attack_technique_name)
            + "</a></td>";
      const acceptCell = `<td><button class="btn btn-success" onclick="acceptAttack('${op.sentence_id}', '${op.attack_uid}')">Accept</button></td>`;
      const ignoreCell = `<td><button class="btn btn-warning" onclick="ignoreAttack('${op.sentence_id}', '${op.attack_uid}')">Ignore</button></td>`;
      const rejectCell = `<td><button class="btn btn-danger" onclick="rejectAttack('${op.sentence_id}', '${op.attack_uid}')">Reject</button></td>`;
      const techniqueRow = `<tr id="sentence-tid${op.attack_uid.substr(op.attack_uid.length - 4)}">${attackCell}${acceptCell}${ignoreCell}${rejectCell}</tr>`;
      $("#tableSentenceInfo").find("tbody").append(techniqueRow);
    });
  // Else this sentence doesn't have attack data
  } else {
    // If the user is clicking on a sentence that's already highlighted, remove the highlighting
    if ($("#elmt" + sentence_id).hasClass(highlightClass) || $("#img" + sentence_id).hasClass(highlightClassImg)) {
      $("#elmt" + sentence_id).removeClass(highlightClass);
      $("#img" + sentence_id).removeClass(highlightClassImg);
      tempHighlighted = undefined;
      // Indicate to the user no actions can be taken as they have unselected something
      enableSenButtons = false;
    // else this sentence wasn't highlighted before; add the highlighting
    } else {
      $("#elmt" + sentence_id).addClass(highlightClass);
      $("#elmt" + sentence_id).addClass(clickedClass);
      $("#img" + sentence_id).addClass(highlightClassImg);
      tempHighlighted = sentence_id;
    }
  }
  // Permit clicking missing techniques button depending if an image is currently highlighted
  $(missingTechBtn).prop("disabled", $(`.${highlightClassImg}`).length > 0 || !enableSenButtons);
  // Allow sentence-action buttons
  $(delSenBtn).prop("disabled", !enableSenButtons);
  $(iocSwitchSelector).prop("disabled", !enableSenButtons);
  $(iocSuggestionBtnSelector).prop("disabled", !enableSenButtons);
  $(iocSuggestSaveBtnSelector).prop("disabled", !enableSenButtons);
  $(iocUpdateBtnSelector).prop("disabled", !enableSenButtons);
  if (enableSenButtons && iocText) {
    $("#" + iocSavedBoxId).val(iocText);
  }
}

function updateConfirmedContext(data) {
  $("#confirmedSentenceInfo tr").remove();
  $.each(data, function(index, op) {
    // Listing the technique: prefix with the parent-technique (if it is a sub-technique), else just print the name
    var techLabel = op.parent_name ? `${op.parent_name}: ${op.name}` : op.name;
    // Listing the technique dates if there are any saved
    var datesLabel = "unspecified";
    if (op.start_date) {
      datesLabel = op.start_date;
      if (op.end_date) {
        datesLabel += " - " + op.end_date;
      }
    }
    var datesHTML = `<a data-bs-toggle="tooltip" data-bs-placement="top" title="${datesLabel}">`;
    datesHTML += `<span class="fa-regular fa-clock glyphicon glyphicon-time btn-sm float-right ps-1"></span></a>`;
    // The checkbox to update the mappings
    var checkbox = `<div class="d-flex"><input type="checkbox" id="${op.mapping_id}" `;
    checkbox += `class="confirmed-technique report-submission-checkbox"${isCompleted ? " disabled" : ""}>`;
    checkbox += `<label for="${op.mapping_id}"<small>${techLabel}</small></label>${datesHTML}</div>`;
    // Before the attack-name, flag if deprecated/revoked
    var td1 = "<td>" + (op.inactive ? "<b>!</b> " : "") + checkbox + "</td>";
    var tmp = "<tr>" + td1 + "</tr>";
    $("#confirmedSentenceInfo").find("tbody").append(tmp);
  });
  // Display the TTP-dates form if there were confirmed attacks
  $(senTTPForm).prop("hidden", !Boolean(data.length));
}

function updateAttackTime(reportTitle) {
  if (!document.getElementById("ttpDatesForm").reportValidity()) {
    return;
  }
  var startDate = document.getElementById("ttpStartDate").value;
  var endDate = document.getElementById("ttpEndDate").value;
  var mappingList = [];
  $(".confirmed-technique:checked").each(function() {
    mappingList.push($(this).prop("id"));
  });
  if (!mappingList.length) {
    alert("No Confirmed Techniques selected.");
    return;
  }
  restRequest("POST", {"index": "update_attack_time", "start_date": startDate, "end_date": endDate,
                       "mapping_list": mappingList, "report_title": reportTitle},
    // Either refresh the whole page or just the techniques list to display recently-saved dates
    function success(resp) {
      if (resp.refresh_page) {
        page_refresh();
        return;
      }
      if (resp.updated_attacks) {
        restRequest("POST", {"index":"confirmed_attacks", "sentence_id": sentence_id}, updateConfirmedContext);
        document.getElementById("ttpStartDate").value = null;
        document.getElementById("ttpEndDate").value = null;
      }
    }
  );
}

function setReportKeywords(reportTitle) {
  // Get selected aggressors and victims and send request for updating
  var assocObj = {
    country: [],
    countries_all: false,
    region: [],
    regions_all: false,
    group: [],
    categories_all: false
  };
  var requestData = {
    aggressors: JSON.parse(JSON.stringify(assocObj)),
    victims: JSON.parse(JSON.stringify(assocObj))
  };
  requestData.victims.category = [];
  $(".aggressorGroupOpt:selected").each(function() {
    requestData.aggressors.group.push($(this).prop("value"));
  });
  $(".aggressorRegionOpt:selected").each(function() {
    requestData.aggressors.region.push($(this).prop("value"));
  });
  $(".aggressorCountryOpt:selected").each(function() {
    requestData.aggressors.country.push($(this).prop("value"));
  });
  $(".victimRegionOpt:selected").each(function() {
    requestData.victims.region.push($(this).prop("value"));
  });
  $(".victimCountryOpt:selected").each(function() {
    requestData.victims.country.push($(this).prop("value"));
  });
  $(".categoryOpt:selected").each(function() {
    requestData.victims.category.push($(this).prop("value"));
  });
  requestData.victims.countries_all = $("input#victimCountrySelAll").prop("checked");
  requestData.victims.categories_all = $("input#victimCategorySelAll").prop("checked");
  restRequest("POST", {"index":"set_report_keywords", "report_title": reportTitle, "victims": requestData.victims,
                       "aggressors": requestData.aggressors},
    // Either refresh the whole page or just the keywords section
    function success(resp) {
      if (resp.refresh_page) {
        page_refresh();
        return;
      }
      setAggressorsVictimsLists();
    }
  );
}

function setAggressorsVictimsLists() {
  generateMultiSelectList("aggressorGroupOpt", "aggressorCurrentGroupList", "aggressorGroupLi");
  generateMultiSelectList("aggressorCountryOpt", "aggressorCurrentCountryList", "aggressorCountryLi");
  generateMultiSelectList("aggressorRegionOpt", "aggressorCurrentRegionList", "aggressorRegionLi");
  generateMultiSelectList("victimRegionOpt", "victimCurrentRegionList", "victimRegionLi");
  generateMultiSelectList("victimCountryOpt", "victimCurrentCountryList", "victimCountryLi");
  generateMultiSelectList("categoryOpt", "currentCategoryList", "reportCategoryLi");
}

function generateMultiSelectList(selOptClass, ulID, liClass) {
  // Remove currently displayed list and rebuild a new list with the recently saved values
  $("ul#" + ulID + " li").remove();
  $("." + selOptClass + ":selected").each(function() {
    var tempLi = "<li class='" + liClass + "' id=" + $(this).prop("value") + ">" + $(this).prop("text") + "</li>";
    $("ul#" + ulID).append(tempLi);
  });
}

function onchangeAggressorGroups(e) {
  updateMultiSelectList(e, "aggressorGroupOpt", "aggressorCurrentGroupList", "aggressorGroupLi", false);
}

function onchangeAggressorRegions(e) {
  updateMultiSelectList(e, "aggressorRegionOpt", "aggressorCurrentRegionList", "aggressorRegionLi");

  // updateCountrySelect("aggressor");
}

function onchangeAggressorCountries(e) {
  updateMultiSelectList(e, "aggressorCountryOpt", "aggressorCurrentCountryList", "aggressorCountryLi");
}

function onchangeVictimRegions(e) {
  updateMultiSelectList(e, "victimRegionOpt", "victimCurrentRegionList", "victimRegionLi");

  // updateCountrySelect("victim");
}

function onchangeVictimCountries(e) {
  updateMultiSelectList(e, "victimCountryOpt", "victimCurrentCountryList", "victimCountryLi");
  // If the list is updated after interacting with individual select-options, this means select-all is n/a
  $("#victimCountrySelAll").prop("checked", false);
}

function onchangeReportCategories(e) {
  updateMultiSelectList(e, "categoryOpt", "currentCategoryList", "reportCategoryLi");
  $("#victimCategorySelAll").prop("checked", false);
}

function onchangeSelectAllKeywords(e, assocType, assocWith) {
  var selectId = assocType + assocWith;
  // Unselect all dropdown options if select-all is checked
  if ($(e).prop("checked")) {
    $("#" + selectId + "Select").selectpicker("deselectAll");
    // Ensure the checkbox stays checked (as unselect-onchange-triggers will revert this)
    $("#" + selectId + "SelAll").prop("checked", true);
  }
}

function updateCountrySelect(assocType) {
  const currentCountrySelection = $(`#${assocType}CountrySelect`).val();
  $(`#${assocType}CountrySelect`).empty();
  $(`#${assocType}CountrySelect`).selectpicker("destroy");

  const selectedRegionIds = $(`#${assocType}RegionSelect`).val();
  // If there are no selected regions, display all countries
  if (selectedRegionIds.length === 0) {
    for (let countryKey in countryRegions) {
      $(`#${assocType}CountrySelect`).append(
        `<option class='${assocType}CountryOpt' value='${countryKey}'>
          ${countries[countryKey]}
        </option>`);
    }
    $(`#${assocType}CountrySelect`).selectpicker('val', currentCountrySelection);
  } else {
    // Display countries from selected regions
    let displayedCountries = [];
    for (let countryKey in countryRegions) {
      let listOverlap = selectedRegionIds.filter(function (item) { return countryRegions[countryKey].includes(item); });
      if (listOverlap.length) {
        $(`#${assocType}CountrySelect`).append(
          `<option class='${assocType}CountryOpt' value='${countryKey}'>
            ${countries[countryKey]}
          </option>`);
        displayedCountries.push(countryKey);
      }
    }
    let selectedDisplayed = displayedCountries.filter(function (item) { return currentCountrySelection.includes(item); });
    $(`#${assocType}CountrySelect`).selectpicker('val', selectedDisplayed);
  }

  $(`#${assocType}CountrySelect`).selectpicker("render");
  updateMultiSelectList(document.getElementById(`${assocType}CountrySelect`), `${assocType}CountryOpt`,
    `${assocType}CurrentCountryList`, `${assocType}CountryLi`);
}

function updateMultiSelectList(dropdown, selOptClass, ulID, liClass, useSelToLookupDisplay=true) {
  var selectedValues = $(dropdown).val();
  var displayedValues = [];
  var liClassTemp = liClass + "Temp";
  // Loop through originally displayed li-items
  $("ul#" + ulID + " li." + liClass).each(function() {
    var valKey = $(this).prop("id");
    displayedValues.push(valKey);
    if (selectedValues.includes(valKey)) {
      // The selected value is already displayed; display no plus/delete signs
      $(this).children('.list-delta').remove();
    } else {
      // This is a displayed value that has been unselected; display the delete symbol if it is not already there
      if (!$(this).children('.list-delta').length) {
        $(this).prepend(remLiHTML);
      }
    }
  });
  // Loop through any temporarily added values (new selections)
  $("ul#" + ulID + " li." + liClassTemp).each(function() {
    var valKey = $(this).prop("id");
    if (!selectedValues.includes(valKey)) {
      // This was selected and then unselected; remove the li
      $(this).remove();
    }
  });
  // Add new li's for newly-selected values if they do not already have an li
  var newlySelected = selectedValues.filter(x => !displayedValues.includes(x));
  for (var newValue of newlySelected) {
    if (!$("ul#" + ulID + " li[id='"  + newValue + "']").length) {
      var valName = useSelToLookupDisplay ? $("." + selOptClass + "[value='" + newValue + "']").prop("text") : newValue;
      var tempLi = "<li class='" + liClassTemp + "' id=" + newValue + ">" + addLiHTML + valName + "</li>";
      $("ul#" + ulID).append(tempLi);
    }
  }
}

function initialiseCountrySelects() {
  for (let assocType of ["aggressor", "victim"]) {
    let selectedRegionIds = $(`#${assocType}RegionSelect`).val();
    if (selectedRegionIds && selectedRegionIds.length) {
      updateCountrySelect(assocType);
    }
  }
}

function importFont() {
  // Obtain the filepath of the JSON containing the font
  var vfsPath = $("script#arachneVfsJson").data("json-path");
  // If we have a filepath...
  if (vfsPath) {
    // Obtain the JSON
    $.getJSON(vfsPath, function(data) {
      // Ensure that pdfMake has a VFS ready
      pdfMake.vfs = pdfMake.vfs || {};
      // Update pdfMake's VFS with the JSON we just retrieved
      Object.assign(pdfMake.vfs, data);
      // Obtain the font .ttf names from what is currently in pdfMake's VFS
      var currentFonts = Object.keys(pdfMake.vfs);
      // Obtain the font .ttf names from what we specified in the config global variable
      var specifiedFonts = Object.values(exoConfig);
      // If all .ttf filenames that we are specifying in our config is in the pdfMake VFS...
      if (specifiedFonts.every(val => currentFonts.includes(val))) {
        // Then the font is now ready to use
        exoFontReady = true;
      }
    });
  }
}

function downloadPDF(data) {
  var generatedPDF;
  // If the font is not ready, try to import it again
  if (!exoFontReady) {
    importFont();
  }
  // Check if we have a logo; if so, add the logo to the PDF
  var imageFilename = "Arachne-Logo.png";
  var imageEncoded = pdfMake.vfs[imageFilename];
  if (imageEncoded) {
    data["background"] = function(currentPage, pageSize) {
      return {image: imageFilename, width: 50, absolutePosition: {x: pageSize.width-70, y: pageSize.height-60}};
    };
  }
  // If the font is ready to use...
  if (exoFontReady) {
    // Update the default-font and pass it into the createPdf() font parameter
    data["defaultStyle"] = {font: "Exo"};
    generatedPDF = pdfMake.createPdf(data, null, {Exo: exoConfig});
  } else {
    // If the font was not ready, create the PDF with pdfMake's defaults
    generatedPDF = pdfMake.createPdf(data);
  }
  // Finish the method by downloading the generated PDF
  generatedPDF.download(data["info"]["title"]);
}

function divSentenceReload() {
  $("#sentenceContextSection").load(document.URL +  " #sentenceContextSection");
}

function autoHeight() {
  if ($("html").height() < $(window).height()) {
    $("footer").addClass("sticky-footer");
  } else {
    $("footer").removeClass("sticky-footer");
  }
}

function addDeleteListener() {
  // Add event listener for DEL button keypress if not added already
  if (!document.delListener) {
    document.addEventListener("keydown", function(event) {
      // Check the button pressed
      if (event.key === "Delete") {
        // Check if there is a delete-sentence button on the page and if it is enabled
        if ($(delSenBtn).length && !$(delSenBtn).prop("disabled")) {
          // Prompt user if they want to delete this sentence
          remove_sentence();
        }
      }
    });
    // Update flag so this is not added again
    document.delListener = true;
  }
}

function addMissingTechnique() {
  if (!document.getElementById("missingTechniqueSelect").reportValidity()) {
    return;
  }
  // If an image is currently not highlighted (don't imply images can be mapped to attacks)
  if($(`.${highlightClassImg}`).length == 0) {
    uid = $("#missingTechniqueSelect :selected").val();
    acceptAttack(sentence_id, uid);
    // If an attack has been added to a temporarily highlighted sentence, the highlighting isn't temporary anymore
    tempHighlighted = undefined
  }
}

function viewMyReports() {
  if (!isLocal) {
    restRequest("POST", {}, page_refresh, "/thread/myreports/view");
  }
}

function exitMyReports() {
  if (!isLocal) {
    restRequest("POST", {}, page_refresh, "/thread/myreports/exit");
  }
}

function privateReportCheck(field) {
  if (!isLocal) {
    // Check if submitting a private report; change the public-confirmation required and hidden properties based on this
    var isPrivate = $(field).is(":checked");
    // Make the confirmation checkbox required if not a private submission
    var checkboxID = $(field).data("paired-checkbox");
    $(checkboxID).prop("required", !isPrivate);
    // Hide the checkbox and accompanying label if a private submission
    var checkboxDivID = $(checkboxID).data("parent-div");
    var wasHidden = $(checkboxDivID).prop("hidden");
    // If we are changing the hidden property (i.e. going from display > hidden and vice-versa), uncheck the box
    if (wasHidden != isPrivate) {
      $(checkboxID).prop("checked", false);
    }
    // Finish by hiding or displaying the confirmation checkbox
    $(checkboxDivID).prop("hidden", isPrivate);
  }
}

function dateRangeChecked(field) {
  var ticked = $(field).prop("checked");
  // Hide and reset the end date input value
  $("#endDateDiv").prop("hidden", ticked);
  $("#endDate").val("");
}

function scrollAndSelectSentence(sentenceId) {
  // If there's a matching sentence-ID, mimic a user clicking on it (get-context) and scroll to it
  var sentenceElem = document.getElementById(`elmt${sentenceId}`);
  if (sentenceElem) {
    sentenceContext(sentenceId);
    sentenceElem.scrollIntoView();
  }
}

function suggestIoC() {
  if (sentence_id) {
    restRequest("POST", {"index": "suggest_indicator_of_compromise", "sentence_id": sentence_id}, function(data) {
      $(iocSuggestionBoxSelector).val(data);
    });
  }
}

function suggestSaveIoC() {
  if (sentence_id) {
    restRequest("POST", {"index": "suggest_and_save_ioc", "sentence_id": sentence_id}, function(data) {
      if (data?.ioc_text) {
        $("#" + iocSavedBoxId).val(data.ioc_text);
        $(`#elmt${sentence_id}`).attr("data-ioc", "true");
        $(`#ioc-icon-${sentence_id}`).show();
      }
    });
  }
}

function addIoC(updating=false) {
  if (sentence_id && document.getElementById(iocSavedBoxId).reportValidity()) {
    var endpoint = updating ? "update_indicator_of_compromise" : "add_indicator_of_compromise";
    restRequest("POST",
      {"index": endpoint, "sentence_id": sentence_id, "ioc_text": $("#" + iocSavedBoxId).val()},
      function() {
        $(`#elmt${sentence_id}`).attr("data-ioc", "true");
        $(`#ioc-icon-${sentence_id}`).show();
        $(iocSuggestionBoxSelector).val("");
      }, restUrl, onError=function() {
        $("#" + iocSavedBoxId).val("");
      }
    );
  }
}

function toggleIoc() {
  if (sentence_id) {
    if ($(`#elmt${sentence_id}`).attr("data-ioc") === "true") {
      restRequest("POST", {"index": "remove_indicator_of_compromise", "sentence_id": sentence_id}, function() {
        $(`#elmt${sentence_id}`).attr("data-ioc", "false");
        $(`#ioc-icon-${sentence_id}`).hide();
        $(iocSuggestionBoxSelector).val("");
        $("#" + iocSavedBoxId).val("");
      });
    } else {
      addIoC();
    }
  }
}

// onDocumentReady function bind
$(document).ready(function() {
  $("header").css("height", $(".navbar").outerHeight());
  autoHeight();
  // onResize bind of the function
  $(window).resize(function() {
    autoHeight();
  });
  // addDeleteListener(); inputs are now interacted with when a sentence is selected
  isCompleted = $("script#reportDetails").data("completed");
  importFont();
  // initialiseCountrySelects();
});
