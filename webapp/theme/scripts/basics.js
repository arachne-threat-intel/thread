// NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

// The current sentence that's selected
var sentence_id = 0;
// A temporarily highlighted sentence
var tempHighlighted = undefined;
// The classes used for highlighting a sentence or image
var highlightClass = "bg-warning";
var highlightClassImg = "imgHighlight";
// The class used when a sentence is clicked
var clickedClass = "report-sentence-clicked";
// ID selectors for report-sentence buttons
var delSenBtn = "#delSenBtn";
var missingTechBtn = "#missingTechBtn";
// The URL for the rest requests
var restUrl = $('script#basicsScript').data('rest-url');
// If this script is being run locally
var isLocal = $('script#basicsScript').data('run-local');
// External-font-loading: pdfMake-config and boolean to represent if we loaded the font
var exoConfig = {
  normal: 'Exo-Light.ttf',
  bold: 'Exo-Bold.ttf',
  italics: 'Exo-Italic.ttf',
  bolditalics: 'Exo-BoldItalic.ttf'
};
var exoFontReady = false;

function restRequest(type, data, callback=null, url=restUrl) {
  $.ajax({
    url: url,
    type: type,
    contentType: 'application/json',
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
   }
  });
}

function page_refresh() {
  window.location.reload(true);
}

function prefixHttp(urlInput) {
  // Obtain the current urls for this input box and loop through them
  var initialInput = urlInput.value;
  var urls = initialInput?.split(",") || [];
  var updateUrl = false;
  for (let i = 0; i < urls.length; i++) {
    // Trim url and check if not empty
    let url = urls[i]?.trim();
    // Skip if there is no url
    if (!url) {
      continue;
    }
    // Proceed to prefix with http if http(s) has not been specified
    if(!(/^https?:\/\//i.test(url))){
      url = "http://" + url;
      updateUrl = true;
    }
    // Update urls list with current url
    urls[i] = url;
  }
  if (updateUrl) {
    // Rejoin elements and update input
    urlInput.value = urls.join(", ");
    // Revert to initial value if invalid
    if (!urlInput.reportValidity()) {
      urlInput.value = initialInput;
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
    truncated = sen_text.split(' ').slice(0,3).join(' ');
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
    // Remove the element itself and any related elements (e.g. buffering <br>s)
    selected.remove();
    $(`.elmtRelated${sentence_id}`).remove();
    // Nothing is currently selected after this removal
    tempHighlighted = undefined;
    // Disable further actions until another item is selected
    $(missingTechBtn).prop("disabled", true);
    $(delSenBtn).prop("disabled", true);
    // Send off request to delete from the db
    restRequest('POST', {'index':'remove_sentence', 'sentence_id': sentence_id});
  }
}

function acceptAttack(id, attack_uid) {
  restRequest('POST', {'index':'add_attack', 'sentence_id': id, 'attack_uid': attack_uid});
  sentenceContext(id, attack_uid);
}

function rejectAttack(id, attack_uid) {
  restRequest('POST', {'index':'reject_attack', 'sentence_id': id, 'attack_uid': attack_uid});
  sentenceContext(id, attack_uid);
}

function deleteReport(reportTitle) {
  if (confirm('Are you sure you want to delete this report?')) {
    restRequest('POST', {'index': 'delete_report', 'report_title': reportTitle}, page_refresh);
  }
}

function rollbackReport(reportTitle) {
  if (confirm('Are you sure you want to rollback this report to NEEDS REVIEW?')) {
    restRequest('POST', {'index': 'rollback_report', 'report_title': reportTitle}, page_refresh);
  }
}

function finish_analysis(reportTitle) {
  if (confirm('Are you sure you are finished with this report?')) {
    restRequest('POST', {'index':'set_status', 'set_status': 'completed', 'report_title': reportTitle}, page_refresh);
  }
}

function submit(data, submitButton) {
  // Do extra checks if this is not locally run
  if(!isLocal) {
    // IDs of fields related to input of Thread token
    var tokenFieldID = $(submitButton).data("token-field-id");
    var checkboxID = $(tokenFieldID).data("paired-checkbox");
    // Check confirmation checkbox
    if (!document.getElementById(checkboxID.replace("#", "")).reportValidity()) {
      return;
    }
    // Update request-data with token
    data.token = $(tokenFieldID).val();
  }
  restRequest('POST', data, page_refresh);
}

function submit_report(submitButton) {
  // The URL and title field values comma-separated
  var url = document.getElementById("url");
  var urls = url.value.split(",");
  var title = document.getElementById("title");
  var titles = title.value.split(",");
  // Notify user that the number of URLs and titles aren't equal
  if (titles.length != urls.length) {
    alert("Number of URLs and titles do not match, please insert same number of comma-separated items.");
  // Proceed with submitting if both fields are valid
  } else if (url.reportValidity() && title.reportValidity()) {
    submit({'index':'insert_report', 'url':urls, 'title':titles}, submitButton);
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
      submit({'index': 'insert_csv', 'file': evt.target.result}, uploadButton);
    }
    reader.onerror = function(evt) {
      alert("Error reading file");
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
    $("footer").addClass('sticky-footer');
  } else {
    $("footer").removeClass('sticky-footer');
  }
}

function sentenceContext(data) {
  // Update selected sentence global variable
  sentence_id = data;
  // Fire off requests to get info on this sentence
  restRequest('POST', {'index':'sentence_context', 'sentence_id': data}, updateSentenceContext);
  restRequest('POST', {'index':'confirmed_attacks', 'sentence_id': data}, updateConfirmedContext);
}

function updateSentenceContext(data) {
  // If we previously highlighted a sentence before and this is a new sentence, remove the previous highlighting
  if (tempHighlighted !== undefined && tempHighlighted !== sentence_id) {
    $("#elmt" + tempHighlighted).removeClass(highlightClass);
    $("#img" + tempHighlighted).removeClass(highlightClassImg);
    tempHighlighted = undefined;
  }
  // Regardless of what is clicked, remove any previous clicked-styling for report sentences
  $(".report-sentence").removeClass(clickedClass);
  // Reset any 'Techniques Found' list
  $("#tableSentenceInfo tr").remove();
  // Flag we will enable any disabled sentence buttons
  enableSenButtons = true;
  // If this sentence has attacks, display the attacks as normal
  if (data && data.length > 0) {
    // Highlight to the user this sentence has been clicked
    $("#elmt" + sentence_id).addClass(clickedClass);
    $.each(data, function(index, op) {
      // For the href, replace any '.' in the TID with a '/' as that is the URL format for sub-techniques
      td1 = "<td><a href=https://attack.mitre.org/techniques/" + op.attack_tid.replace(".", "/") + " target=_blank>"
            // Prefix the name with the parent-technique (if it is a sub-technique), else just print the name
            + (op.attack_parent_name ? `${op.attack_parent_name}: ${op.attack_technique_name}` : op.attack_technique_name)
            + "</a></td>";
      td2 = `<td><button class='btn btn-success' onclick='acceptAttack("${op.sentence_id}", "${op.attack_uid}")'>Accept</button></td>`;
      td3 = `<td><button class='btn btn-danger' onclick='rejectAttack("${op.sentence_id}", "${op.attack_uid}")'>Reject</button></td>`;
      tmp = `<tr id="sentence-tid${op.attack_uid.substr(op.attack_uid.length - 4)}">${td1}${td2}${td3}</tr>`;
      $("#tableSentenceInfo").find('tbody').append(tmp);
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
  // Allow 'remove selected' button
  $(delSenBtn).prop("disabled", !enableSenButtons);
}

function updateConfirmedContext(data) {
  $("#confirmedSentenceInfo tr").remove();
  $.each(data, function(index, op) {
    // Prefix the name with the parent-technique (if it is a sub-technique), else just print the name
    td1 = "<td>" + (op.parent_name ? `${op.parent_name}: ${op.name}` : op.name) + "</td>"
    tmp = "<tr>" + td1 + "</tr>"
    $("#confirmedSentenceInfo").find('tbody').append(tmp);
  });
}

function importFont() {
  // Obtain the filepath of the JSON for the font
  var exoPath = $("script#exoFontJson").data("json-path");
  // If we have a filepath...
  if (exoPath) {
    // Obtain the JSON
    $.getJSON(exoPath, function(data) {
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
  // If the font is ready to use...
  if (exoFontReady) {
    // Update the default-font and pass it into the createPdf() font parameter
    data['defaultStyle'] = {font: 'Exo'};
    generatedPDF = pdfMake.createPdf(data, null, {Exo: exoConfig});
  } else {
    // If the font was not ready, create the PDF with pdfMake's defaults
    generatedPDF = pdfMake.createPdf(data);
  }
  // Finish the method by downloading the generated PDF
  generatedPDF.download(data['info']['title']);
}

function downloadLayer(data) {
  // Create the name of the JSON download file from the name of the report
  var json = JSON.parse(data)
  var filename = json["filename"] + ".json";
  // We don't need to include the filename property within the file
  delete json["filename"];
  // Encode updated json as a uri component
  var dataStr = "text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(json));
  // Create temporary DOM element with attribute values needed to perform the download
  var a = document.createElement('a');
  a.href = 'data:' + dataStr;
  a.download = filename;
  a.innerHTML = 'download JSON';
  // Add the temporary element to the DOM
  var container = document.getElementById('dropdownMenu');
  container.appendChild(a);
  // Download the JSON document
  a.click();
  // Remove the temporary element from the DOM
  a.remove();
}

function viewLayer(data) {
  console.info("viewLayer: " + data)
}

function divSentenceReload() {
  $('#sentenceContextSection').load(document.URL +  ' #sentenceContextSection');
}

function autoHeight() {
  if ($("html").height() < $(window).height()) {
    $("footer").addClass('sticky-footer');
  } else {
    $("footer").removeClass('sticky-footer');
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
  // If an image is currently not highlighted (don't imply images can be mapped to attacks)
  if($(`.${highlightClassImg}`).length == 0) {
    uid = $("#missingTechniqueSelect :selected").val();
    acceptAttack(sentence_id, uid);
    // If an attack has been added to a temporarily highlighted sentence, the highlighting isn't temporary anymore
    tempHighlighted = undefined
  }
}

function myReports() {
  if (!isLocal) {
    var tokenField = document.getElementById("token");
    if (tokenField.reportValidity()) {
      restRequest("POST", {"token": tokenField.value}, page_refresh, "/thread/myreports/view");
    }
  }
}

function myReportsExit() {
  if (!isLocal) {
    restRequest("POST", {}, page_refresh, "/thread/myreports/exit");
  }
}

function tokenFieldCheck(field) {
  if (!isLocal) {
    // Check the token field has a value; change the public-confirmation required and hidden properties based on this
    var hasValue = Boolean($(field).val().length);
    // Make the confirmation checkbox required if there is no value for the token field
    var checkboxID = $(field).data("paired-checkbox");
    $(checkboxID).prop("required", !hasValue);
    // Hide the checkbox and accompanying label if there is a value
    var checkboxDivID = $(checkboxID).data("parent-div");
    var wasHidden = $(checkboxDivID).prop("hidden");
    // If we are changing the hidden property (i.e. going from display > hidden and vice-versa), uncheck the box
    if (wasHidden != hasValue) {
      $(checkboxID).prop("checked", false);
    }
    // Finish by hiding or displaying the confirmation checkbox
    $(checkboxDivID).prop("hidden", hasValue);
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
  addDeleteListener();
  importFont();
});
