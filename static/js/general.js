let number

$(document).ready(function(){
//    $('data-bs-toggle=["tooltip"]').tooltip();

//    const popover = new bootstrap.Popover($("#popover-test"))

//    $('[data-bs-toggle="popover"]').hide(200);

    $('[data-bs-toggle="popover"]').popover({
      trigger: 'focus'
    })

    number = 2;

});

function changeVisibility() {
    $("#mainWord").toggle(0);
    console.log( "Change Visibility Function Ran" );
}

//Currently Using In VV Story
function showNextSentence() {
    console.log(number);
    $("#sentence-" + number).show(200);
    number += 1;
}


