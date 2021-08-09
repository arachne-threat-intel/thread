// The current sentence that's selected
var sentence_id = 0;
// A temporarily highlighted sentence
var tempHighlighted = undefined;
// The classes used for highlighting a sentence or image
var highlightClass = "bg-warning";
var highlightClassImg = "imgHighlight";

function restRequest(type, data, callback) {
    $.ajax({
        url: '/rest',
        type: type,
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(data) {
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
        if (!urlInput.checkValidity()) {
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
        // Prepare the first three words of the sentence as a reminder to the user of the sentence that is selected
        sen_text = selectedSentence.text;
        truncated = sen_text.split(' ').slice(0,3).join(' ');
        // Add trailing ellipsis if the sentence has more than three words
        truncated += (truncated == sen_text) ? "" : "...";
        messageInfo = `sentence ("${truncated.trim()}")`;
        // Flag selected to be this sentence to be removed
        selected = selectedSentence;
    } else if (selectedImage) {  // Else if an image is selected
        messageInfo = "image";
        // Flag selected to be this image to be removed
        selected = selectedImage;
    } else {  // Else we do not have an item selected for removal
        alert("Unable to determine selected item in report. Please try refreshing page.");
        return;
    }
    // Confirm with the user that this is being removed
    if (confirm("Are you sure you want to remove the currently selected " + messageInfo
        + "? This can only be retrieved by re-submitting this report.")) {
        // Remove the element itself and any related elements (e.g. buffering <br>s)
        selected.remove();
        $(`.elmtRelated${sentence_id}`).remove();
        // Nothing is currently selected after this removal
        tempHighlighted = undefined;
        // Disable further actions until another item is selected
        $("#missingTechBtn").prop("disabled", true);
        $("#delSenBtn").prop("disabled", true);
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

function finish_analysis(reportTitle) {
    if (confirm('Are you sure you are finished with this report?')) {
        restRequest('POST', {'index':'set_status', 'set_status': 'completed', 'report_title': reportTitle}, page_refresh);
    }
}

function submit_report() {
    // The URL and title field values comma-separated
    var url = document.getElementById("url");
    var urls = url.value.split(",");
    var title = document.getElementById("title");
    var titles = title.value.split(",");
    // Notify user that the number of URLs and titles aren't equal
    if (titles.length != urls.length) {
      alert("Number of URLs and titles do not match, please insert same number of comma separated items.");
    // Proceed with submitting if both fields are valid
    } else if (title.checkValidity() && url.checkValidity()) {
      restRequest('POST', {'index':'insert_report', 'url':urls, 'title':titles});
    }
}

function upload_file() {
    // console.log(document.getElementById("csv_file"))
    var file = document.getElementById("csv_file").files[0];
    if(file) {
        var reader = new FileReader();
        reader.readAsText(file, "UTF-8");
        reader.onload = function(evt) {
            // console.log(evt.target.result)
            restRequest('POST', {'index': 'insert_csv', 'file': evt.target.result});
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
    // Reset any 'Techniques Found' list
    $("#tableSentenceInfo tr").remove();
    // Flag we will enable any disabled sentence buttons
    enableSenButtons = true;
    // If this sentence has attacks, display the attacks as normal
    if (data && data.length > 0) {
        $.each(data, function(index, op) {
            td1 = "<td><a href=https://attack.mitre.org/techniques/" + op.attack_tid + " target=_blank>" + op.attack_technique_name + "</a></td>";
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
            $("#img" + sentence_id).addClass(highlightClassImg);
            tempHighlighted = sentence_id;
        }
    }
    // Permit clicking missing techniques button depending if an image is currently highlighted
    $("#missingTechBtn").prop("disabled", $(`.${highlightClassImg}`).length > 0 || !enableSenButtons);
    // Allow 'remove selected' button
    $("#delSenBtn").prop("disabled", !enableSenButtons);
}

function updateConfirmedContext(data) {
    $("#confirmedSentenceInfo tr").remove();
    $.each(data, function(index, op) {
        td1 = "<td>" + op.name + "</td>"
        tmp = "<tr>" + td1 + "</tr>"
        $("#confirmedSentenceInfo").find('tbody').append(tmp);
    });
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

 // onDocumentReady function bind
$(document).ready(function() {
    $("header").css("height", $(".navbar").outerHeight());
    autoHeight();
});

// onResize bind of the function
$(window).resize(function() {
    autoHeight();
});

function addMissingTechnique() {
    // If an image is currently not highlighted (don't imply images can be mapped to attacks)
    if($(`.${highlightClassImg}`).length == 0) {
        uid = $("#missingTechniqueSelect :selected").val();
        acceptAttack(sentence_id, uid);
        // If an attack has been added to a temporarily highlighted sentence, the highlighting isn't temporary anymore
        tempHighlighted = undefined
    }
}
