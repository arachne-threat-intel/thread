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
       success:function(data) { callback(data); },
       error: function (xhr, ajaxOptions, thrownError) { console.log(thrownError); }
    });
}

function remove_sentences(){
    var sentence_id =  document.getElementById("sentence_id").value;
    restRequest('POST', {'index':'remove_sentences', 'sentence_id':sentence_id}, show_info);
}

function acceptAttack(id, attack_uid) {
    restRequest('POST', {'index':'add_attack', 'sentence_id': id, 'attack_uid': attack_uid}, show_info);
    sentenceContext(id, attack_uid);
}

function rejectAttack(id, attack_uid) {
    restRequest('POST', {'index':'reject_attack', 'sentence_id': id, 'attack_uid': attack_uid}, show_info);
    sentenceContext(id, attack_uid);
}

function deleteReport(report_id){
  if (confirm('Are you sure you want to delete this report?')) {
    restRequest('POST', {'index':'delete_report', 'report_id':report_id}, show_info)
    window.location.reload(true);
  } else {}

}

function set_status(set_status, file_name){
    restRequest('POST', {'index':'set_status', 'set_status':set_status, 'file_name':file_name}, show_info);
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
      restRequest('POST', {'index':'insert_report', 'url':urls, 'title':titles}, show_info);
    }
}

function upload_file(){
  //var fileName = this.val().split("\\").pop();

  console.log(document.getElementById("csv_file"))
  var file = document.getElementById("csv_file").files[0];
  if(file){
    var reader = new FileReader();
    reader.readAsText(file, "UTF-8");
    reader.onload = function(evt){
      console.log(evt.target.result)
      restRequest('POST', {'index':'insert_csv','file':evt.target.result},show_info);
    }
    reader.onerror = function(evt){
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

function show_info(data){
    console.log(data.status);
}

function savedAlert(){
    console.log("saved");
}

 function autoHeight() {
    if ($("html").height() < $(window).height()) {
      $("footer").addClass('sticky-footer');
    } else {
      $("footer").removeClass('sticky-footer');
    }
}

function sentenceContext(data, attack_uid) {
    // Update selected sentence global variable
    sentence_id = data;
    // Fire off requests to get info on this sentence
    restRequest('POST', {'index':'sentence_context', 'uid': data, 'attack_uid': attack_uid}, updateSentenceContext);
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
        // else this sentence wasn't highlighted before; add the highlighting
        } else {
            $("#elmt" + sentence_id).addClass(highlightClass);
            $("#img" + sentence_id).addClass(highlightClassImg);
            tempHighlighted = sentence_id;
        }
    }
    // Permit clicking missing techniques button depending if an image is currently highlighted
    $("#missingTechBtn").prop("disabled", $(`.${highlightClassImg}`).length > 0);
}

function updateConfirmedContext(data) {
    $("#confirmedSentenceInfo tr").remove();
    $.each(data, function(index, op) {
        td1 = "<td>" + op.name + "</td>"
        tmp = "<tr>" + td1 + "</tr>"
        $("#confirmedSentenceInfo").find('tbody').append(tmp);
    });
}

function downloadLayer(data){
  // Create the name of the JSON download file from the name of the report
  var json = JSON.parse(data) 
  var title = json['name'] //document.getElementById("title").value;
  var filename = title + ".json";
  // Encode data as a uri component
  var dataStr = "text/json;charset=utf-8," + encodeURIComponent(data);
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

function viewLayer(data){
  console.info("viewLayer: " + data)
}

function divSentenceReload(){
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
        restRequest('POST', {'index':'add_attack', 'sentence_id': sentence_id, 'attack_uid':uid}, show_info);
        restRequest('POST', {'index':'confirmed_attacks', 'sentence_id': sentence_id}, updateConfirmedContext);
        // If an attack has been added to a temporarily highlighted sentence, the highlighting isn't temporary anymore
        tempHighlighted = undefined
    }
}
